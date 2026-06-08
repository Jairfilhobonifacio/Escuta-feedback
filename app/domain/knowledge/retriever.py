"""KnowledgeBase — busca por similaridade no corpus (pgvector).

Recupera os trechos mais próximos da pergunta do contato, filtrando por
organização e por um piso de similaridade (groundedness): se nada passa do
piso, devolve lista vazia → o brain não tem contexto → cai no fallback honesto
("vou encaminhar ao time"), em vez de alucinar.

SQL cru de propósito: a coluna `embedding` é pgvector, fora do ORM (ver
app/models/knowledge.py). Postgres-only; os testes usam dublês.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings import EmbeddingService, to_pgvector

logger = logging.getLogger(__name__)

DEFAULT_K = 4
# Piso de similaridade de cosseno (0..1). MiniLM costuma dar ~0.4-0.7 em match
# bom de FAQ; abaixo de ~0.30 quase sempre é ruído. Conservador de propósito.
DEFAULT_MIN_SCORE = 0.30


@dataclass
class RetrievedChunk:
    title: str
    content: str
    score: float


class KnowledgeBase:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID, embedder: EmbeddingService):
        self.session = session
        self.org_id = organization_id
        self.embedder = embedder

    async def search(
        self, query: str, k: int = DEFAULT_K, min_score: float = DEFAULT_MIN_SCORE
    ) -> list[RetrievedChunk]:
        qvec = to_pgvector(await self.embedder.embed_one(query))
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT title, content,
                           1 - (embedding <=> CAST(:q AS vector)) AS score
                    FROM knowledge_chunks
                    WHERE organization_id = :org AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:q AS vector)
                    LIMIT :k
                    """
                ),
                {"q": qvec, "org": str(self.org_id), "k": k},
            )
        ).all()
        return [
            RetrievedChunk(title=r.title, content=r.content, score=float(r.score))
            for r in rows
            if float(r.score) >= min_score
        ]
