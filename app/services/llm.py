"""Cliente LLM (Groq, API OpenAI-compatible) — fino e à prova de queda.

Princípio: o LLM é um ENRIQUECEDOR, nunca um ponto de falha. `chat_json`
devolve dict ou None — jamais lança. Timeout curto: melhor cair no fluxo
determinístico do que segurar o webhook do WhatsApp.

Roteamento por tarefa (plano do produto): Groq cobre o tempo real (interpretar
resposta, classificar feedback). Tarefas de raciocínio longo (digest, copilot)
entram na Fase 1 com outro provider.
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

    def __init__(self, api_key: str, model: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat_json(self, system: str, user: str) -> dict[str, Any] | None:
        """Uma rodada system+user com response_format=json_object.

        Retorna o JSON parseado ou None (erro de rede/HTTP/parse/timeout).
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "temperature": 0.2,
                        "max_tokens": 400,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
            if resp.status_code != 200:
                logger.warning("GroqLLM: HTTP %s — %.200s", resp.status_code, resp.text)
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001 — LLM nunca derruba o fluxo.
            logger.warning("GroqLLM: falha na chamada (rede/timeout/parse)", exc_info=True)
            return None
