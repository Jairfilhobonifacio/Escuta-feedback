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

    async def send_text(self, chat_id: str, text: str, session: Optional[str] = None) -> Dict[str, Any]:
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

    async def send_image(self, chat_id: str, image_url: str, caption: str = "", session: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "chatId": self._to_chat_id(chat_id),
            "file": {"url": image_url},
            "caption": caption,
            "session": session or self.default_session,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/sendImage", json=payload, headers=self._headers())
        return {"success": r.status_code < 400, "data": r.text}

    async def send_audio(self, chat_id: str, audio_url: str, session: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "chatId": self._to_chat_id(chat_id),
            "file": {"url": audio_url},
            "session": session or self.default_session,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/sendVoice", json=payload, headers=self._headers())
        return {"success": r.status_code < 400, "data": r.text}

    async def resolve_lid(self, lid: str, session: Optional[str] = None) -> Optional[str]:
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

    async def get_contacts(self, session: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"session": session or self.default_session}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/api/contacts/all", params=params, headers=self._headers())
        return r.json() if r.status_code < 400 else []

    async def get_session_status(self, session: Optional[str] = None) -> Optional[str]:
        """Status da sessão WAHA (best-effort) — ex.: 'WORKING', 'SCAN_QR_CODE'.

        GET /api/sessions/{session} -> {"name": ..., "status": "WORKING"}. Retorna a
        string de status quando o WAHA responde, ou None quando indisponível/erro
        (mesmo padrão dos outros métodos: try/except + log, nunca derruba).
        """
        sess = session or self.default_session
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/api/sessions/{sess}", headers=self._headers()
                )
            if r.status_code >= 400:
                logger.warning("WAHA session status %s: %s", r.status_code, r.text[:200])
                return None
            return (r.json() or {}).get("status")
        except Exception:  # noqa: BLE001 — status é best-effort; WAHA off -> None.
            logger.exception("WAHA get_session_status falhou")
            return None

    async def is_connected(self, session: Optional[str] = None) -> bool:
        """True só se a sessão WAHA está plenamente conectada ('WORKING')."""
        return (await self.get_session_status(session)) == "WORKING"

    async def get_qr_code(self, session: Optional[str] = None) -> Dict[str, Any]:
        """QR Code da sessão WAHA para parear (best-effort).

        GET /api/{session}/auth/qr?format=image -> PNG binário (content-type
        image/...) ou, em versões antigas, JSON {"value"/"qr": "<base64|texto>"}.
        Monta um data-uri quando vem binário/base64 cru. Retorna sempre o mesmo
        contrato: {"qr": <data-uri|str|None>, "status": <str|None>}. WAHA off/erro
        (ou já WORKING, que não expõe QR) -> {"qr": None, "status": <status|None>}.
        Mesmo padrão dos outros métodos: try/except + log, nunca derruba.
        """
        import base64 as _b64

        sess = session or self.default_session
        status = await self.get_session_status(sess)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/api/{sess}/auth/qr",
                    params={"format": "image"},
                    headers=self._headers(),
                )
            if r.status_code >= 400:
                logger.warning("WAHA get_qr_code %s: %s", r.status_code, r.text[:200])
                return {"qr": None, "status": status}

            content_type = r.headers.get("content-type", "")
            # PNG binário -> data-uri.
            if "image" in content_type:
                b64 = _b64.b64encode(r.content).decode("utf-8")
                return {"qr": f"data:image/png;base64,{b64}", "status": status}

            # JSON antigo: {"value"/"qr": ...}. Pode vir base64 cru ou já data-uri.
            try:
                data = r.json() or {}
                value = data.get("value") or data.get("qr")
                if value and isinstance(value, str) and not value.startswith("data:"):
                    value = f"data:image/png;base64,{value}"
                return {"qr": value, "status": status}
            except ValueError:
                # Corpo não-JSON e não-imagem: devolve o texto cru como veio.
                text = (r.text or "").strip()
                return {"qr": text or None, "status": status}
        except Exception:  # noqa: BLE001 — QR é best-effort; WAHA off -> qr None.
            logger.exception("WAHA get_qr_code falhou")
            return {"qr": None, "status": status}

    async def start_session(self, session: Optional[str] = None) -> Dict[str, Any]:
        """Inicia a sessão WAHA para parear (best-effort).

        POST /api/sessions/start com body {"name": session} (mesmo endpoint do
        Nexus). Retorna {"ok": bool, "status": <str|None>}; o status é relido após
        o start (tipicamente STARTING/SCAN_QR_CODE). WAHA off/erro -> ok False.
        Mesmo padrão dos outros métodos: try/except + log, nunca derruba.
        """
        sess = session or self.default_session
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/sessions/start",
                    json={"name": sess},
                    headers=self._headers(),
                )
            ok = r.status_code < 400
            if not ok:
                logger.warning("WAHA start_session %s: %s", r.status_code, r.text[:200])
        except Exception:  # noqa: BLE001 — start é best-effort; WAHA off -> ok False.
            logger.exception("WAHA start_session falhou")
            ok = False
        return {"ok": ok, "status": await self.get_session_status(sess)}

    async def stop_session(self, session: Optional[str] = None) -> Dict[str, Any]:
        """Para a sessão WAHA (best-effort).

        POST /api/sessions/stop com body {"name": session} (mesmo endpoint do
        Nexus). Retorna {"ok": bool, "status": <str|None>}; status relido após o
        stop (tipicamente STOPPED/None). WAHA off/erro -> ok False. Mesmo padrão
        dos outros métodos: try/except + log, nunca derruba.
        """
        sess = session or self.default_session
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/sessions/stop",
                    json={"name": sess},
                    headers=self._headers(),
                )
            ok = r.status_code < 400
            if not ok:
                logger.warning("WAHA stop_session %s: %s", r.status_code, r.text[:200])
        except Exception:  # noqa: BLE001 — stop é best-effort; WAHA off -> ok False.
            logger.exception("WAHA stop_session falhou")
            ok = False
        return {"ok": ok, "status": await self.get_session_status(sess)}

    async def restart_session(self, session: Optional[str] = None) -> Dict[str, Any]:
        """Reinicia a sessão WAHA = stop + start (best-effort).

        O WAHA não tem endpoint dedicado de restart no fluxo do Nexus, então
        encadeamos stop seguido de start (ambos best-effort). Retorna o resultado
        do start: {"ok": bool, "status": <str|None>}. ok=True se o start subiu,
        mesmo que o stop anterior não tenha encontrado sessão para parar.
        """
        sess = session or self.default_session
        await self.stop_session(sess)
        return await self.start_session(sess)

    async def check_number_exists(self, phone: str, session: Optional[str] = None) -> Optional[bool]:
        """Checa se um número está registrado no WhatsApp (best-effort).

        GET /api/contacts/check-exists?phone=...&session=... — resposta típica
        {"numberExists": true/false}. Retorna True/False quando o WAHA responde, ou
        None quando o WAHA está indisponível/erro (mesmo padrão dos outros métodos:
        try/except + log, nunca derruba). `phone` é só os dígitos (sem @c.us).
        """
        params = {"phone": str(phone).split("@", 1)[0], "session": session or self.default_session}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    f"{self.base_url}/api/contacts/check-exists", params=params, headers=self._headers()
                )
            if r.status_code >= 400:
                logger.warning("WAHA check-exists %s: %s", r.status_code, r.text[:200])
                return None
            exists = (r.json() or {}).get("numberExists")
            return bool(exists) if exists is not None else None
        except Exception:  # noqa: BLE001 — checagem é best-effort; WAHA off -> None.
            logger.exception("WAHA check_number_exists falhou para %s", phone)
            return None
