"""Embeddings locais (sentence-transformers) — sem custo de API, sem rede.

Modelo all-MiniLM-L6-v2 (384 dims), o mesmo dim do Nexus, já em cache nesta
máquina. Forçamos modo offline: a 1ª chamada NÃO pode tentar baixar (o TLS do
antivírus quebraria) — o modelo tem de estar no cache do HuggingFace.

O encode é síncrono e pesado (CPU); exponho `embed`/`embed_one` async que
rodam em thread para não travar o event loop do webhook. Singleton lazy: o
modelo carrega na 1ª busca e fica quente.
"""
from __future__ import annotations

import asyncio
import os
from functools import lru_cache

# Precisa vir antes de qualquer import do huggingface_hub/sentence_transformers.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384


class EmbeddingService:
    """Encoder lazy. `embed*` devolvem vetores L2-normalizados (cosine = dot)."""

    def __init__(self, model_name: str = EMBED_MODEL):
        self._model_name = model_name
        self._model = None  # carregado sob demanda

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_sync, texts)

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingService:
    """Singleton de processo — o modelo é caro de carregar."""
    return EmbeddingService()


def to_pgvector(vec: list[float]) -> str:
    """Serializa um vetor para o literal aceito pelo pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
