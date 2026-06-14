"""Dublês de teste — implementações fake das interfaces de domínio.

`FakeMessagingService` satisfaz o Protocol `IMessagingService` (só o que o
dispatcher usa: `send_text`). Guarda cada envio em `self.sent` para asserts e
devolve um id de mensagem fixo, simulando o retorno da WAHA.

`FakeEmbedder` / `FakeLLM` servem ao Clustering de Dores (Camada 1): o embedder
devolve um vetor fixo 384d (testa o reindex sem carregar o MiniLM); o LLM devolve
um JSON de rótulo fixo e conta as chamadas (testa a rotulagem do engine sem Groq).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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


class FakeEmbedder:
    """Dublê do EmbeddingService: devolve um vetor fixo 384d por texto (sem MiniLM).

    `embed` é o método que o reindex usa em lote; `embed_one` (usado pelo inline) cai
    no mesmo vetor. Guarda em `self.calls` os textos vistos, para asserts.
    """

    def __init__(self, dim: int = 384, value: float = 0.05) -> None:
        self.dim = dim
        self.value = value
        self.calls: List[List[str]] = []

    async def embed(self, texts: List[str]) -> List[List[float]]:
        self.calls.append(list(texts))
        return [[self.value] * self.dim for _ in texts]

    async def embed_one(self, text: str) -> List[float]:
        return (await self.embed([text]))[0]


class FakeLLM:
    """Dublê do GroqLLM para a rotulagem de clusters: `chat_json` devolve um JSON fixo.

    Conta as chamadas em `self.calls` (o engine rotula 1×/cluster, best-effort). Por
    padrão devolve um rótulo plausível; `payload=None` simula o LLM indisponível.
    """

    def __init__(self, payload: Optional[Dict[str, Any]] = ...) -> None:
        if payload is ...:
            payload = {
                "label": "Dor de teste",
                "description": "Clientes reclamam do mesmo assunto.",
                "dominant_sentiment": "negativo",
            }
        self.payload = payload
        self.calls: List[Dict[str, str]] = []

    async def chat_json(self, system: str, user: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        self.calls.append({"system": system, "user": user})
        return self.payload
