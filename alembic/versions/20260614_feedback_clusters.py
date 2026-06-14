"""feedback_clusters + embeddings (Camada 1 — Clustering Semântico de Dores)

Ver docs/CLUSTERING_DORES_SPEC.md §1.

Cria:
- tabela `feedback_clusters` (a DOR descoberta): id, organization_id (FK CASCADE),
  label (NULL), description (NULL), dominant_sentiment (NULL), item_count (DEFAULT 0),
  improvement_id (FK SET NULL), created_at, updated_at + `centroid vector(384)`.
- colunas novas em `feedback_items`: `cluster_id` (FK feedback_clusters SET NULL) e
  `embedding vector(384)`.

Colunas/índices pgvector são Postgres-only e moram em `op.execute()` (igual à
migration de knowledge_chunks): a coluna `vector` e os índices HNSW de cosseno não
existem no SQLite dos testes. As colunas portáveis e os índices simples
(ix_feedback_clusters_org, ix_feedback_items_cluster_id) vão no schema normal.

`CREATE EXTENSION IF NOT EXISTS vector` é defensivo (a base do RAG já o tem).

Revision ID: 20260614_feedback_clusters
Revises: 20260613_playbooks_cs_tasks
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260614_feedback_clusters"
down_revision: Union[str, None] = "20260613_playbooks_cs_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector deve estar disponível (a base do RAG já o instala) — defensivo.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- feedback_clusters (a dor) -------------------------------------------
    op.create_table(
        "feedback_clusters",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("dominant_sentiment", sa.String, nullable=True),
        sa.Column("item_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "improvement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("improvements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_clusters_org", "feedback_clusters", ["organization_id"])
    op.create_index("ix_feedback_clusters_improvement", "feedback_clusters", ["improvement_id"])
    # Coluna pgvector + HNSW cosseno (PG-only).
    op.execute("ALTER TABLE feedback_clusters ADD COLUMN centroid vector(384)")
    op.execute(
        "CREATE INDEX ix_feedback_clusters_centroid_hnsw ON feedback_clusters "
        "USING hnsw (centroid vector_cosine_ops)"
    )

    # --- feedback_items: cluster_id (portável) + embedding (pgvector) --------
    op.add_column(
        "feedback_items",
        sa.Column(
            "cluster_id",
            UUID(as_uuid=True),
            sa.ForeignKey("feedback_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_feedback_items_cluster_id", "feedback_items", ["cluster_id"])
    op.execute("ALTER TABLE feedback_items ADD COLUMN embedding vector(384)")
    op.execute(
        "CREATE INDEX ix_feedback_items_embedding_hnsw ON feedback_items "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_feedback_items_embedding_hnsw")
    op.drop_index("ix_feedback_items_cluster_id", table_name="feedback_items")
    op.drop_column("feedback_items", "embedding")
    op.drop_column("feedback_items", "cluster_id")

    op.execute("DROP INDEX IF EXISTS ix_feedback_clusters_centroid_hnsw")
    op.drop_index("ix_feedback_clusters_improvement", table_name="feedback_clusters")
    op.drop_index("ix_feedback_clusters_org", table_name="feedback_clusters")
    op.drop_table("feedback_clusters")
