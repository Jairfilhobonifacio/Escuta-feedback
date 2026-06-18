"""VoCAgentOrchestrator — o loop de tool-calling do Agente de Voz do Cliente.

Conduz a conversa: o LLM decide (texto final OU pedir tools) → o registry executa as
tools pedidas → os resultados voltam ao LLM → repete, até o modelo responder sem pedir
mais tools OU bater o TETO de iterações. Devolve o texto final + um rastro do que foi
feito (tools executadas, nº de iterações, se terminou naturalmente).

Garantias (espelham o never-raises do resto do projeto):
- `chat_with_tools` já é à prova de queda (retorna resultado neutro em falha/circuito
  aberto). Ainda assim, TODO o loop roda numa caixa try/except: nada aqui derruba o
  webhook. Em falha, devolve um resultado seguro (reply vazio, completed=False).
- TETO de iterações (`max_iterations`): impede loop infinito se o modelo insistir em
  pedir tools. Ao estourar, sai com `completed=False` e o melhor texto que tiver.
- O agente é DORMENTE: só é instanciado/rodado pelo resolver quando
  `settings.voc_agent_enabled` é True. Com a flag OFF, este módulo nem é importado.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.domain.voc.registry import VoCToolRegistry
from app.services.llm import GroqLLM

logger = logging.getLogger(__name__)

# Persona/instruções do agente. Mantido conservador: o agente AGE sobre o CRM (tools)
# e/ou responde ao cliente; nunca inventa fatos. O envio de WhatsApp pode estar
# desligado/bloqueado — o agente deve tratar isso como normal (a tool avisa).
DEFAULT_SYSTEM_PROMPT = (
    "Você é o Agente de Voz do Cliente de uma empresa (português do Brasil). Seu trabalho "
    "é cuidar dos feedbacks dos clientes no WhatsApp: entender o que a pessoa disse, agir no "
    "CRM quando fizer sentido (registrar abordagem, rotear para um time, criar tarefa, vincular "
    "a uma melhoria, atualizar status) e, quando apropriado, responder ao cliente de forma "
    "calorosa e honesta. Use as ferramentas disponíveis para agir; consulte o perfil do contato "
    "antes de decidir. Nunca invente fatos sobre a empresa (preços, prazos, políticas). Se o "
    "envio de WhatsApp estiver desligado ou bloqueado, siga normalmente — apenas não terá enviado "
    "a mensagem. Seja conciso."
)

# Teto padrão de idas-e-voltas com o modelo. Cada iteração = 1 chamada ao LLM (+
# possivelmente N tools). Suficiente para encadear algumas tools sem risco de loop.
DEFAULT_MAX_ITERATIONS = 5


@dataclass
class VoCAgentResult:
    """Resultado de uma execução do agente.

    - `reply`: texto final do assistant para o cliente (pode ser "" — ex.: o agente só
      agiu no CRM e não tem nada a dizer, ou a chamada caiu).
    - `tool_calls_made`: nomes das tools executadas, em ordem (para auditoria/teste).
    - `iterations`: quantas rodadas de LLM aconteceram.
    - `completed`: True se o modelo terminou naturalmente (sem pedir mais tools);
      False se estourou o teto ou caiu numa falha.
    """

    reply: str = ""
    tool_calls_made: list[str] = field(default_factory=list)
    iterations: int = 0
    completed: bool = False


class VoCAgentOrchestrator:
    def __init__(
        self,
        llm: GroqLLM,
        registry: VoCToolRegistry,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_iterations = max(1, int(max_iterations))
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _initial_messages(
        self, user_message: str, history: Optional[list[tuple[str, str]]]
    ) -> list[dict[str, Any]]:
        """Monta a conversa inicial (system + histórico + a mensagem atual do cliente).

        `history` = [(direction, body)] em ordem cronológica; 'in*'=cliente (user),
        o resto = assistant. A mensagem atual entra como último user (sem duplicar se
        já for a última do histórico)."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        last_pair: Optional[tuple[str, str]] = None
        for direction, body in history or []:
            role = "user" if str(direction).lower().startswith("in") else "assistant"
            messages.append({"role": role, "content": body})
            last_pair = (direction, body)
        already = (
            last_pair is not None
            and str(last_pair[0]).lower().startswith("in")
            and last_pair[1] == user_message
        )
        if not already:
            messages.append({"role": "user", "content": user_message})
        return messages

    async def run(
        self, user_message: str, history: Optional[list[tuple[str, str]]] = None
    ) -> VoCAgentResult:
        """Roda o loop até a resposta final ou o teto. NUNCA levanta."""
        result = VoCAgentResult()
        try:
            return await self._run_loop(user_message, history, result)
        except Exception:  # noqa: BLE001 — o agente nunca derruba o webhook.
            logger.warning("VoCAgentOrchestrator: falha no loop — saída segura", exc_info=True)
            return result

    async def _run_loop(
        self,
        user_message: str,
        history: Optional[list[tuple[str, str]]],
        result: VoCAgentResult,
    ) -> VoCAgentResult:
        messages = self._initial_messages(user_message, history)
        tools = self.registry.as_tools()

        for _ in range(self.max_iterations):
            result.iterations += 1
            chat = await self.llm.chat_with_tools(
                messages,
                tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if not chat.has_tool_calls:
                # Resposta final do modelo (ou neutra em falha): encerra o loop.
                content = chat.message.get("content") if isinstance(chat.message, dict) else None
                result.reply = (content or "").strip() if isinstance(content, str) else ""
                result.completed = True
                return result

            # O modelo pediu tools: reanexa a mensagem do assistant e executa cada uma,
            # devolvendo o resultado como mensagem role="tool" amarrada pelo tool_call_id.
            messages.append(chat.message)
            for call in chat.tool_calls:
                content = await self.registry.dispatch(call)
                result.tool_calls_made.append(call.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": content,
                    }
                )
            # volta ao topo: o modelo agora vê os resultados e decide o próximo passo.

        # Estourou o teto sem o modelo concluir: saída segura (completed=False).
        logger.warning(
            "VoCAgentOrchestrator: teto de %d iterações atingido — encerrando", self.max_iterations
        )
        return result
