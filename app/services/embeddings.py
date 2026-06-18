"""Embeddings locais (sentence-transformers) — sem custo de API, sem rede.

Modelo all-MiniLM-L6-v2 (384 dims), o mesmo dim do Nexus, já em cache nesta
máquina. Forçamos modo offline: a 1ª chamada NÃO pode tentar baixar (o TLS do
antivírus quebraria) — o modelo tem de estar no cache do HuggingFace.

O encode é síncrono e pesado (CPU); exponho `embed`/`embed_one` async que
rodam em thread para não travar o event loop do webhook. Singleton lazy: o
modelo carrega na 1ª busca e fica quente.

Modelo parametrizável por `settings.embedding_model_name` (lido só no singleton
`get_embedder`): VAZIO ("") = exatamente o modelo atual (all-MiniLM-L6-v2, 384d)
— ZERO regressão. Para nuance em PORTUGUÊS, o recomendado é
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (também 384d → NÃO
muda a coluna `vector(384)`, NÃO exige migration). A troca é um passo MANUAL:
exige o modelo no cache HF (HF_HUB_OFFLINE=1) + re-gerar os vetores (reindex),
pois vetores de modelos diferentes NÃO são comparáveis no mesmo espaço.
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache

# Precisa vir antes de qualquer import do huggingface_hub/sentence_transformers.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logger = logging.getLogger(__name__)

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384
# Recomendado para PT (também 384d → sem migration). Documental: a troca é manual
# (cache HF + reindex) via EMBEDDING_MODEL_NAME; não é carregado por default.
MULTILINGUAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _resolve_model_name() -> str:
    """Nome do modelo a carregar: `settings.embedding_model_name` se setado, senão
    o default histórico (all-MiniLM-L6-v2). Vazio ("") ⇒ ZERO regressão.

    Import tardio de `settings` para não acoplar este módulo (importado cedo) ao
    config e para refletir o estado atual da env quando o singleton é criado.
    """
    try:
        from app.config import settings

        name = (settings.embedding_model_name or "").strip()
    except Exception:  # noqa: BLE001 — sem config acessível, mantém o default.
        name = ""
    return name or EMBED_MODEL


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
    """Singleton de processo — o modelo é caro de carregar.

    O nome do modelo vem de `settings.embedding_model_name` (vazio ⇒ default
    histórico, sem regressão). Como é cacheado, a env é lida UMA vez por processo;
    trocar o modelo em runtime exige reiniciar (e re-gerar os vetores).
    """
    model_name = _resolve_model_name()
    if model_name != EMBED_MODEL:
        logger.info("embeddings: usando modelo customizado %r (≠ default)", model_name)
    return EmbeddingService(model_name)


def to_pgvector(vec: list[float]) -> str:
    """Serializa um vetor para o literal aceito pelo pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
