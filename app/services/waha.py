"""WAHAService — implementação concreta de IMessagingService (canal WhatsApp).

Versão mínima inspirada no `app/services/waha.py` do Nexus. Na Fase 1 copiamos a
versão completa (retry/backoff, circuit breaker `waha_breaker`, sessões Plus).
Na Fase 2, uma `CloudApiMessagingService` entra ao lado, sem mexer no resto.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class WAHAService:
    """Implementa IMessagingService falando com um gateway WAHA."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, default_session: str = "default", timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_session = default_session
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    @staticmethod
    def _to_chat_id(phone: str) -> str:
        """5524999214290 -> 5524999214290@c.us (idempotente)."""
        return phone if "@" in phone else f"{phone}@c.us"

    async def send_text(self, chat_id: str, text: str, session: str = None) -> Dict[str, Any]:
        payload = {
            "chatId": self._to_chat_id(chat_id),
            "text": text,
            "session": session or self.default_session,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/api/sendText", json=payload, headers=self._headers())
            if r.status_code >= 400:
                logger.warning("WAHA sendText %s: %s", r.status_code, r.text[:200])
                return {"error": r.text, "status_code": r.status_code}
            return {"success": True, "data": r.json()}
        except Exception as exc:  # noqa: BLE001 — Fase 1 adiciona retry/backoff + circuit breaker
            logger.exception("WAHA sendText falhou")
            return {"error": str(exc)}

    async def send_image(self, chat_id: str, image_url: str, caption: str = "", session: str = None) -> Dict[str, Any]:
        payload = {
            "chatId": self._to_chat_id(chat_id),
            "file": {"url": image_url},
            "caption": caption,
            "session": session or self.default_session,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/sendImage", json=payload, headers=self._headers())
        return {"success": r.status_code < 400, "data": r.text}

    async def send_audio(self, chat_id: str, audio_url: str, session: str = None) -> Dict[str, Any]:
        payload = {
            "chatId": self._to_chat_id(chat_id),
            "file": {"url": audio_url},
            "session": session or self.default_session,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/sendVoice", json=payload, headers=self._headers())
        return {"success": r.status_code < 400, "data": r.text}

    async def resolve_lid(self, lid: str, session: str = None) -> Optional[str]:
        """Resolve um LID (ex.: '77052233408626@lid') para o telefone real.

        O WhatsApp identifica alguns chats (self-chat incluso) por LID em vez do
        número. GET /api/{session}/lids/{lid} -> {"lid": ..., "pn": "55...@c.us"}.
        Retorna só os dígitos do telefone, ou None se não conseguir resolver.
        """
        sess = session or self.default_session
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/api/{sess}/lids/{lid}", headers=self._headers()
                )
            if r.status_code >= 400:
                logger.warning("WAHA resolve_lid %s: %s", r.status_code, r.text[:200])
                return None
            pn = (r.json() or {}).get("pn") or ""
            phone = str(pn).split("@", 1)[0]
            return phone or None
        except Exception:  # noqa: BLE001 — resolução de LID é best-effort.
            logger.exception("WAHA resolve_lid falhou para %s", lid)
            return None

    async def get_contacts(self, session: str = None) -> List[Dict[str, Any]]:
        params = {"session": session or self.default_session}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/api/contacts/all", params=params, headers=self._headers())
        return r.json() if r.status_code < 400 else []
