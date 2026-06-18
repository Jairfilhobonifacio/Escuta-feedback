"""VoCToolRegistry — catálogo de tools do Agente VoC (genérico, sem regra de negócio).

Mantém o registro (nome → descrição + JSON Schema dos parâmetros + executor async),
expõe a lista no formato `tools` que a API do Groq espera e despacha um `ToolCall`
(vindo de `GroqLLM.chat_with_tools`) para o executor certo.

Princípios (espelham o resto do projeto):
- O registry NÃO conhece as tools concretas — o `tools.py` registra os executores já
  com a sessão/org/canal capturados em closure. Isso mantém o registry testável puro.
- DESPACHO never-raises: um executor que levanta NÃO derruba o loop do agente; o erro
  vira um resultado-string ({"ok": false, "error": ...}) que volta ao modelo. Um nome
  de tool desconhecido idem (o modelo às vezes alucina um nome).
- O resultado de cada tool é serializado para STRING (o `content` da mensagem
  role="tool" tem de ser texto). Dict/list viram JSON; o resto, `str()`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.services.llm import ToolCall

logger = logging.getLogger(__name__)

# Um executor recebe os argumentos já parseados (dict) e devolve qualquer coisa
# serializável (dict/list/str/num/bool/None). O registry serializa para string.
ToolExecutor = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema do objeto de argumentos
    executor: ToolExecutor

    def as_groq_tool(self) -> dict[str, Any]:
        """Formato `tools` do Groq (OpenAI-compatible)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _to_content(value: Any) -> str:
    """Serializa o resultado de uma tool para o `content` (texto) da msg role=tool."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


class VoCToolRegistry:
    """Catálogo de tools + despacho. Instância barata (1 por request/agente)."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        executor: ToolExecutor,
    ) -> None:
        """Registra uma tool. Nome duplicado SOBRESCREVE (último vence) com WARN."""
        if name in self._tools:
            logger.warning("VoCToolRegistry: tool %r re-registrada (sobrescrevendo)", name)
        self._tools[name] = RegisteredTool(
            name=name, description=description, parameters=parameters, executor=executor
        )

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def as_tools(self) -> list[dict[str, Any]]:
        """Lista no formato `tools` do Groq (para passar a `chat_with_tools`)."""
        return [t.as_groq_tool() for t in self._tools.values()]

    async def dispatch(self, call: ToolCall) -> str:
        """Executa o `ToolCall` e devolve o `content` (string) da resposta da tool.

        NUNCA levanta: tool desconhecida ou executor que falha viram um JSON de erro
        — assim o modelo recebe o feedback e pode seguir, em vez de quebrar o loop.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            logger.warning("VoCToolRegistry: tool desconhecida %r — ignorando", call.name)
            return _to_content({"ok": False, "error": f"tool desconhecida: {call.name}"})
        try:
            result = await tool.executor(call.arguments or {})
        except Exception as exc:  # noqa: BLE001 — tool nunca derruba o agente.
            logger.warning("VoCToolRegistry: tool %r falhou ao executar", call.name, exc_info=True)
            return _to_content({"ok": False, "error": f"falha ao executar {call.name}: {exc!r}"})
        return _to_content(result)
