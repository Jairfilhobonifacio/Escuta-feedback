"""Cliente LLM (Groq, API OpenAI-compatible) — fino e à prova de queda.

Princípio: o LLM é um ENRIQUECEDOR, nunca um ponto de falha. `chat_json`
devolve dict ou None — jamais lança. Timeout curto: melhor cair no fluxo
determinístico do que segurar o webhook do WhatsApp.

Resiliência de cota: quando o modelo principal estoura o limite diário (429) ou
falha, `chat_json` tenta UMA vez o `fallback_model` (cota separada, normalmente
mais folgada) antes de devolver None. Assim o Survey Agent continua conduzindo
num modelo menor em vez de despencar direto na máquina de estados.

Resiliência de queda (circuit breaker): cada ponto de chamada à API passa por um
`CircuitBreaker`. Se a Groq cair em série (timeouts/erros de rede/5xx), o breaker
abre e as próximas chamadas FALHAM RÁPIDO (sem nem bater na rede) por uma janela
curta — o fluxo cai direto no determinístico em vez de pagar o timeout toda vez.
O breaker conta SÓ falhas reais de chamada; um JSON inválido (erro de validação)
não derruba o circuito. O contrato externo é o mesmo: `chat_json` devolve dict
ou None; `complete` devolve str — JAMAIS lançam.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_TIMEOUT_SECONDS = 8.0

# Status HTTP que contam como FALHA REAL de chamada (alimentam o circuit breaker):
# rate limit e erros de servidor. 4xx "de cliente" (ex.: 400/401/404) são erro de
# configuração nosso, não instabilidade do provedor — não devem abrir o circuito.
_BREAKER_FAILURE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Parâmetros do breaker padrão (compartilhado por todas as instâncias de GroqLLM
# sem breaker injetado). Constantes para que o teste de ciclo de vida e o código
# de produção concordem sobre o threshold/janela.
_BREAKER_FAILURE_THRESHOLD = 3
_BREAKER_RECOVERY_TIMEOUT = 30.0


class _UpstreamError(RuntimeError):
    """Falha REAL de chamada (rede/timeout/5xx/429) — conta pro circuit breaker."""


@dataclass(frozen=True)
class ToolCall:
    """Um pedido de tool feito pelo modelo (function-calling nativo do Groq).

    `arguments` já vem parseado (dict). Se o modelo devolver JSON inválido nos
    argumentos, vira `{}` — o executor decide o que fazer com argumentos vazios
    (não derruba o loop). `id` é o `tool_call_id` que a resposta da tool tem de
    ecoar de volta para o modelo.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatToolResult:
    """Resultado de uma rodada de `chat_with_tools`.

    - `message`: a mensagem do assistant CRUA (formato OpenAI), para reanexar ao
      histórico antes de mandar os resultados das tools. Em falha/circuito aberto
      é uma mensagem neutra (`{"role":"assistant","content":""}`) — nunca None.
    - `tool_calls`: lista de `ToolCall` (vazia = o modelo não pediu tool nenhuma,
      ou a chamada falhou). `has_tool_calls` é o sinal de "continue o loop".
    """

    message: dict[str, Any]
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def _neutral_assistant_message() -> dict[str, Any]:
    """Mensagem neutra do assistant — resultado seguro quando a chamada não rende."""
    return {"role": "assistant", "content": ""}


def _parse_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    """Extrai os `tool_calls` da mensagem do assistant (formato OpenAI/Groq).

    Tolerante por princípio: qualquer entrada malformada é PULADA (não levanta).
    Argumentos vêm como string JSON em `function.arguments`; JSON inválido → `{}`
    (o executor lida com argumentos faltando, sem quebrar o loop).
    """
    raw = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[ToolCall] = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name or not isinstance(name, str):
            continue
        args_raw = fn.get("arguments")
        if isinstance(args_raw, dict):
            args = args_raw
        elif isinstance(args_raw, str) and args_raw.strip():
            try:
                parsed = json.loads(args_raw)
                args = parsed if isinstance(parsed, dict) else {}
            except (ValueError, TypeError):
                logger.warning("tool_call %s: arguments com JSON inválido — usando {}", name)
                args = {}
        else:
            args = {}
        call_id = tc.get("id")
        out.append(ToolCall(id=str(call_id) if call_id else f"call_{name}", name=name, arguments=args))
    return out


def _build_default_breaker() -> CircuitBreaker:
    """Constrói o breaker padrão do GroqLLM (mesmos parâmetros do antigo inline)."""
    return CircuitBreaker(
        failure_threshold=_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout=_BREAKER_RECOVERY_TIMEOUT,
        expected_exception=_UpstreamError,
        name="groq",
    )


# Breaker PADRÃO com ciclo de vida de PROCESSO (singleton de módulo). O `GroqLLM`
# é instanciado por request (ex.: webhook); se cada instância criasse o próprio
# breaker, o contador de falhas zeraria a cada mensagem e o circuito NUNCA abriria
# em produção. Compartilhar um único breaker entre todas as instâncias (sem
# breaker injetado) faz o estado de resiliência PERSISTIR entre requests.
_DEFAULT_BREAKER: CircuitBreaker = _build_default_breaker()


def reset_default_breaker() -> None:
    """Zera o breaker padrão de processo (closed, sem falhas).

    Útil em testes: como o singleton é compartilhado entre instâncias de GroqLLM
    SEM breaker injetado, um teste que abre o circuito contaminaria o próximo.
    Chame antes de cada teste que dependa do breaker padrão.
    """
    _DEFAULT_BREAKER.reset()


class GroqLLM:
    """Chat-completion JSON-mode na Groq. Instância barata (1 por request ok)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        fallback_model: str | None = None,
        breaker: CircuitBreaker | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # Modelo de reserva (cota separada): usado quando o principal falha/estoura.
        self.fallback_model = fallback_model
        # Circuit breaker compartilhado entre os dois modelos (principal + reserva):
        # se a Groq como um todo está fora, abrir uma vez basta. Conta SÓ
        # `_UpstreamError` (rede/timeout/5xx/429), nunca JSON inválido.
        #
        # Sem breaker injetado, usa o SINGLETON de processo (`_DEFAULT_BREAKER`):
        # como o GroqLLM nasce por request, um breaker novo por instância nunca
        # acumularia falhas entre requests e o circuito jamais abriria. Compartilhar
        # o mesmo breaker faz o estado persistir. A injeção (`breaker=`) sobrescreve
        # o singleton — testes isolam o estado passando o próprio breaker.
        self.breaker = breaker or _DEFAULT_BREAKER

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> dict[str, Any] | None:
        """Uma rodada system+user com response_format=json_object.

        Tenta o modelo principal; se ele falhar (429/timeout/erro/parse), tenta UMA
        vez o `fallback_model`. Retorna o JSON parseado ou None.
        `temperature`/`max_tokens` ajustáveis: o Survey Agent usa temperatura um
        pouco maior para respostas naturais e mais espaço para o turno completo.
        """
        data = await self._call(self.model, system, user, temperature, max_tokens)
        if data is not None:
            return data
        if self.fallback_model and self.fallback_model != self.model:
            logger.warning(
                "GroqLLM: modelo principal (%s) indisponível — tentando reserva %s",
                self.model, self.fallback_model,
            )
            return await self._call(self.fallback_model, system, user, temperature, max_tokens)
        return None

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "Você é um assistente conciso. Responda em português do Brasil.",
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str:
        """Completa texto livre (sem JSON-mode). Best-effort: "" em qualquer falha.

        Atalho fino sobre o mesmo cliente/timeout do `chat_json` para quem só quer
        um texto curto (ex.: rotular um cluster de dores). Tenta o modelo principal
        e, se ele falhar, UMA vez o `fallback_model`. NUNCA lança.
        """
        text = await self._call_text(self.model, system, prompt, temperature, max_tokens)
        if text:
            return text
        if self.fallback_model and self.fallback_model != self.model:
            return await self._call_text(self.fallback_model, system, prompt, temperature, max_tokens)
        return ""

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str = "auto",
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> ChatToolResult:
        """Uma rodada de function-calling NATIVO do Groq (API OpenAI-compatible).

        Envia a conversa (`messages`, já no formato OpenAI incluindo system/user/
        assistant/tool) + as `tools` declaradas; devolve a mensagem do assistant e
        os `tool_calls` que o modelo pediu. NUNCA lança e JAMAIS devolve None —
        o contrato é o mesmo dos outros métodos: em falha real (rede/timeout/5xx/
        429), JSON quebrado ou circuito ABERTO, retorna um `ChatToolResult` NEUTRO
        (mensagem vazia, `tool_calls=[]`), para o agente cair no fluxo determinístico
        em vez de pagar o timeout/quebrar o webhook.

        Como `chat_json`/`complete`: tenta o modelo principal e, se ele não render
        (None), tenta UMA vez o `fallback_model` (cota separada). O breaker é o mesmo
        compartilhado — só falhas reais (`_UpstreamError`) o alimentam; um payload
        sem `tool_calls` é resposta legítima, não falha.
        """
        result = await self._call_tools(self.model, messages, tools, tool_choice, temperature, max_tokens)
        if result is not None:
            return result
        if self.fallback_model and self.fallback_model != self.model:
            logger.warning(
                "GroqLLM.chat_with_tools: modelo principal (%s) indisponível — reserva %s",
                self.model, self.fallback_model,
            )
            result = await self._call_tools(
                self.fallback_model, messages, tools, tool_choice, temperature, max_tokens
            )
            if result is not None:
                return result
        # Nem principal nem reserva renderam: resultado neutro (sem tool calls).
        return ChatToolResult(message=_neutral_assistant_message(), tool_calls=[])

    async def _post_message(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST cru no chat/completions que devolve a MENSAGEM inteira do assistant
        (não só o `content`) — necessário para ler `tool_calls`.

        Mesma política de falha do `_post`: levanta `_UpstreamError` em FALHA REAL
        (rede/timeout/5xx/429), que é o que o circuit breaker conta; 4xx "de cliente"
        viram mensagem neutra (não abrem o circuito). Em 200, devolve o dict
        `choices[0].message` (ou neutro se o formato vier estranho)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": model, **payload},
                )
        except Exception as exc:  # rede/timeout: instabilidade do provedor.
            raise _UpstreamError(f"groq[{model}]: erro de rede/timeout: {exc!r}") from exc
        if resp.status_code in _BREAKER_FAILURE_STATUSES:
            raise _UpstreamError(f"groq[{model}]: HTTP {resp.status_code}")
        if resp.status_code != 200:
            logger.warning("GroqLLM[%s]: HTTP %s — %.200s", model, resp.status_code, resp.text)
            return _neutral_assistant_message()
        try:
            message = resp.json()["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError):
            logger.warning("GroqLLM[%s]: resposta de tools em formato inesperado", model)
            return _neutral_assistant_message()
        return message if isinstance(message, dict) else _neutral_assistant_message()

    async def _call_tools(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> ChatToolResult | None:
        """Uma chamada de function-calling a um modelo. None ⇒ falha real/circuito
        aberto (quem chama tenta a reserva e/ou devolve neutro). NUNCA lança.

        O POST passa pelo circuit breaker (falhas reais abrem o circuito); o parse
        dos `tool_calls` fica FORA dele — argumentos malformados não são instabilidade
        do provedor e não contam pro breaker (viram `arguments={}`)."""
        payload: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        try:
            message = await self.breaker.call_async(self._post_message, model, payload)
        except CircuitOpenError:
            logger.warning("GroqLLM.chat_with_tools[%s]: circuito ABERTO — pulando chamada", model)
            return None
        except Exception:  # noqa: BLE001 — LLM nunca derruba o fluxo.
            logger.warning("GroqLLM.chat_with_tools[%s]: falha na chamada (rede/timeout)", model, exc_info=True)
            return None
        return ChatToolResult(message=message, tool_calls=_parse_tool_calls(message))

    async def _post(self, model: str, payload: dict[str, Any]) -> str:
        """POST cru no chat/completions. Levanta `_UpstreamError` em FALHA REAL
        (rede/timeout/5xx/429) — é o que o circuit breaker conta. Devolve o texto
        bruto do `content` (string, possivelmente vazia) em caso de 200."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": model, **payload},
                )
        except Exception as exc:  # rede/timeout: instabilidade do provedor.
            raise _UpstreamError(f"groq[{model}]: erro de rede/timeout: {exc!r}") from exc
        if resp.status_code in _BREAKER_FAILURE_STATUSES:
            raise _UpstreamError(f"groq[{model}]: HTTP {resp.status_code}")
        if resp.status_code != 200:
            # 4xx "de cliente" (config nossa): falha, mas NÃO instabilidade → não abre o circuito.
            logger.warning("GroqLLM[%s]: HTTP %s — %.200s", model, resp.status_code, resp.text)
            return ""
        return resp.json()["choices"][0]["message"]["content"] or ""

    async def _call_text(
        self, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> str:
        """Uma chamada de texto livre a um modelo. "" em qualquer falha (nunca lança).

        Envolve o POST no circuit breaker: aberto ⇒ falha rápido sem tocar a rede.
        """
        payload = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            content = await self.breaker.call_async(self._post, model, payload)
            return (content or "").strip()
        except CircuitOpenError:
            logger.warning("GroqLLM.complete[%s]: circuito ABERTO — pulando chamada", model)
            return ""
        except Exception:  # noqa: BLE001 — LLM nunca derruba o fluxo.
            logger.warning("GroqLLM.complete[%s]: falha na chamada (rede/timeout/parse)", model, exc_info=True)
            return ""

    async def _call(
        self, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> dict[str, Any] | None:
        """Uma chamada a um modelo específico. None em qualquer falha (nunca lança).

        O POST passa pelo circuit breaker (falhas reais abrem o circuito); o parse
        do JSON fica FORA dele — um JSON malformado é erro de validação, não
        instabilidade do provedor, e não deve contar pro breaker.
        """
        payload = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            content = await self.breaker.call_async(self._post, model, payload)
        except CircuitOpenError:
            logger.warning("GroqLLM[%s]: circuito ABERTO — pulando chamada", model)
            return None
        except Exception:  # noqa: BLE001 — LLM nunca derruba o fluxo.
            logger.warning("GroqLLM[%s]: falha na chamada (rede/timeout)", model, exc_info=True)
            return None
        if not content:
            return None
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            logger.warning("GroqLLM[%s]: JSON inválido na resposta", model)
            return None
        return data if isinstance(data, dict) else None
