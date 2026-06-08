"""Model da base de conhecimento (RAG) — knowledge_chunks.

A coluna `embedding vector(384)` existe SÓ no Postgres (criada pela migration)
e é manipulada via SQL cru no ingest/retriever — de propósito NÃO está mapeada
aqui. Assim o `create_all` dos testes (SQLite, sem pgvector) cria a tabela com
as colunas portáveis e os testes usam dublês de retrieval, sem tocar pgvector.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String)        # 'bizzu' / arquivo de origem
    title: Mapped[str] = mapped_column(String)         # título da seção
    content: Mapped[str] = mapped_column(Text)         # texto do chunk
    chunk_metadata: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # NB: coluna `embedding vector(384)` adicionada pela migration (Postgres-only),
    # fora do ORM — ver docstring.
