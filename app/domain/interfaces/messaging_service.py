"""Interface de mensageria — COPIADA do Nexus AI (app/domain/interfaces/messaging_service.py).

É o "ativo" que permite trocar WAHA → WhatsApp Cloud API (BSP) sem reescrever o
resto: dispatcher e resolver dependem só deste Protocol, nunca de uma impl concreta.
"""
from typing import Protocol, Dict, Any, List


class IMessagingService(Protocol):
    """Protocolo (Interface) para serviços de mensageria."""

    async def send_text(self, chat_id: str, text: str, session: str = None) -> Dict[str, Any]:
        """Envia mensagem de texto."""
        ...

    async def send_image(self, chat_id: str, image_url: str, caption: str = "", session: str = None) -> Dict[str, Any]:
        """Envia imagem."""
        ...

    async def send_audio(self, chat_id: str, audio_url: str, session: str = None) -> Dict[str, Any]:
        """Envia áudio."""
        ...

    async def get_contacts(self, session: str = None) -> List[Dict[str, Any]]:
        """Lista contatos."""
        ...
