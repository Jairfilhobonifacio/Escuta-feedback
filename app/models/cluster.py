"""Model do Clustering Semântico de Dores (Camada 1 da Central de Gestão).

Uma `FeedbackCluster` é uma DOR descoberta automaticamente: um grupo de
`feedback_items` cujos textos têm significado próximo (cosseno dos embeddings).
O motor (`app/domain/clustering/engine.py`) lê os itens com `embedding`, agrupa
por similaridade, calcula um centroide e (best-effort, via LLM) dá um rótulo.

Colunas pgvector FORA do ORM (igual a `knowledge_chunks.embedding`):
- `feedback_clusters.centroid vector(384)` — média renormalizada do cluster.
- `feedback_items.embedding vector(384)` — adicionada pela migration.
Ambas existem SÓ no Postgres (criadas pela migration) e são manipuladas por SQL
cru no engine/reindex. Mapeá-las aqui quebraria o `create_all` do SQLite nos
testes (não há tipo `vector`). Ver docstring de app/models/knowledge.py.

O vínculo `feedback_items.cluster_id -> feedback_clusters.id` (ON DELETE SET NULL)
ESTÁ no ORM (coluna portável): apagar uma dor solta os feedbacks, não os apaga.
Multi-tenant por `organization_id`. Os enums (dominant_sentiment) são validados
na API/engine, sem CHECK no banco (vocabulário pode crescer), igual ao resto.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeedbackCluster(Base):
    __tablename__ = "feedback_clusters"
    __table_args__ = (
        # Índice simples por org (o HNSW sobre `centroid` fica na migration, PG-only).
        Index("ix_feedback_clusters_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    # Título da dor, gerado pelo LLM ("Dificuldade com acesso à conta"). NULL = sem rótulo.
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    # 1 parágrafo descrevendo a dor (LLM). NULL = sem descrição.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sentimento mais frequente entre os itens: 'positivo' | 'neutro' | 'negativo'.
    dominant_sentiment: Mapped[str | None] = mapped_column(String, nullable=True)
    # Cache do nº de itens no cluster, atualizado a cada run.
    item_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Liga a dor a uma melhoria do roadmap (usado no Roadmap depois). NULL = solta.
    # ON DELETE SET NULL: apagar a melhoria não apaga a dor.
    improvement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("improvements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    # NB: coluna `centroid vector(384)` adicionada pela migration (Postgres-only),
    # fora do ORM — ver docstring do módulo.
