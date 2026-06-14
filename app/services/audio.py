"""Transcrição de áudio inbound do WhatsApp via Groq Whisper (best-effort).

O cliente manda um áudio no WhatsApp → o webhook baixa (URL do WAHA ou base64) e
transcreve aqui via Groq (`whisper-large-v3`, OpenAI-compatible). O texto volta e o
fluxo trata como se a pessoa tivesse digitado. Best-effort: NUNCA lança — retorna o
texto ou None (sem chave / download falho / transcrição falha), e o webhook acolhe.
"""
from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

_GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def _download(url: str, waha_api_key: str | None, timeout: float) -> bytes | None:
    """Baixa a mídia do WAHA. Repassa X-Api-Key (a URL pode exigir auth)."""
    headers = {"X-Api-Key": waha_api_key} if waha_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            logger.warning("audio: download falhou HTTP %s", r.status_code)
            return None
        return r.content
    except Exception:  # noqa: BLE001
        logger.warning("audio: download falhou (rede/timeout)", exc_info=True)
        return None


async def transcribe_audio(
    *,
    url: str | None = None,
    data_b64: str | None = None,
    mimetype: str | None = None,
    waha_api_key: str | None = None,
    groq_api_key: str | None = None,
    groq_model: str = "whisper-large-v3",
    timeout: float = 45.0,
) -> str | None:
    """Obtém os bytes do áudio (base64 ou URL) e transcreve via Groq Whisper.

    Retorna o texto transcrito (pt-BR) ou None. Best-effort, nunca lança.
    """
    if not groq_api_key:
        return None

    audio: bytes | None = None
    if data_b64:
        try:
            audio = base64.b64decode(data_b64)
        except Exception:  # noqa: BLE001
            audio = None
    if audio is None and url:
        audio = await _download(url, waha_api_key, timeout)
    if not audio:
        return None

    # Extensão a partir do mimetype (audio/ogg -> ogg); fallback 'ogg' (PTT do WhatsApp).
    ext = "ogg"
    if mimetype and "/" in mimetype:
        ext = (mimetype.split("/", 1)[1].split(";", 1)[0] or "ogg")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                _GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {groq_api_key}"},
                files={"file": (f"audio.{ext}", audio, mimetype or "audio/ogg")},
                data={"model": groq_model, "language": "pt"},
            )
        if r.status_code >= 400:
            logger.warning("audio: Groq Whisper HTTP %s — %.200s", r.status_code, r.text)
            return None
        text = (r.json().get("text") or "").strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("audio: transcrição Groq falhou", exc_info=True)
        return None
