"""Dublês de teste — implementações fake das interfaces de domínio.

`FakeMessagingService` satisfaz o Protocol `IMessagingService` (só o que o
dispatcher usa: `send_text`). Guarda cada envio em `self.sent` para asserts e
devolve um id de mensagem fixo, simulando o retorno da WAHA.
"""
from __future__ import annotations

from typing import Any, Dict, List


class FakeMessagingService:
    """Fake de IMessagingService: registra envios e devolve um id fixo."""

    def __init__(self, msg_id: str = "fake-msg-1") -> None:
        self.msg_id = msg_id
        self.sent: List[Dict[str, Any]] = []

    async def send_text(self, chat_id: str, text: str, session: str = None) -> Dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, "session": session})
        return {"data": {"id": self.msg_id}}

    async def send_image(self, chat_id: str, image_url: str, caption: str = "", session: str = None) -> Dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "image_url": image_url, "caption": caption, "session": session})
        return {"data": {"id": self.msg_id}}

    async def send_audio(self, chat_id: str, audio_url: str, session: str = None) -> Dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "audio_url": audio_url, "session": session})
        return {"data": {"id": self.msg_id}}

    async def get_contacts(self, session: str = None) -> List[Dict[str, Any]]:
        return []
