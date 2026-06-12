"""Cliente LLM (Groq, API OpenAI-compatible) — fino e à prova de queda.

Princípio: o LLM é um ENRIQUECEDOR, nunca um ponto de falha. `chat_json`
devolve dict ou None — jamais lança. Timeout curto: melhor cair no fluxo
determinístico do que segurar o webhook do WhatsApp.

Resiliência de cota: quando o modelo principal estoura o limite diário (429) ou
falha, `chat_json` tenta UMA vez o `fallback_model` (cota separada, normalmente
mais folgada) antes de devolver None. Assim o Survey Agent continua conduzindo
num modelo menor em vez de despencar direto na máquina de estados.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_TIMEOUT_SECONDS = 8.0


class GroqLLM:
    """Chat-completion JSON-mode na Groq. Instância barata (1 por request ok)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        fallback_model: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # Modelo de reserva (cota separada): usado quando o principal falha/estoura.
        self.fallback_model = fallback_model

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

    async def _call(
        self, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> dict[str, Any] | None:
        """Uma chamada a um modelo específico. None em qualquer falha (nunca lança)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
            if resp.status_code != 200:
                logger.warning("GroqLLM[%s]: HTTP %s — %.200s", model, resp.status_code, resp.text)
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001 — LLM nunca derruba o fluxo.
            logger.warning("GroqLLM[%s]: falha na chamada (rede/timeout/parse)", model, exc_info=True)
            return None
