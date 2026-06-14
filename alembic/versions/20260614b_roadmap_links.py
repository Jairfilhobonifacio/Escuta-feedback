"""roadmap_links — liga melhorias a dores + esforço/data-alvo (Camada 3 — Roadmap & Melhorias)

Ver docs/ROADMAP_MELHORIAS_SPEC.md §1.

Adiciona à tabela `improvements` (tudo aditivo/portável — sem pgvector, roda no
SQLite dos testes):
- `cluster_id UUID REFERENCES feedback_clusters(id) ON DELETE SET NULL` (nullable) —
  a melhoria responde a uma dor (cluster semântico). Fecha o par com a coluna já
  existente `feedback_clusters.improvement_id`.
- `effort VARCHAR NULL` — 'P'/'M'/'G'/'XG' (sem CHECK no banco; valida na API).
- `target_date TIMESTAMPTZ NULL` — data-alvo exibida no roadmap.
Índice `ix_improvements_cluster_id`.

`feedback_clusters` já existe (migration 20260614_feedback_clusters), então a FK
pode ser criada inline aqui.

Revision ID: 20260614b_roadmap_links
Revises: 20260614_feedback_clusters
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260614b_roadmap_links"
down_revision: Union[str, None] = "20260614_feedback_clusters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "improvements",
        sa.Column(
            "cluster_id",
            UUID(as_uuid=True),
            sa.ForeignKey("feedback_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("improvements", sa.Column("effort", sa.String, nullable=True))
    op.add_column(
        "improvements",
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_improvements_cluster_id", "improvements", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_improvements_cluster_id", table_name="improvements")
    op.drop_column("improvements", "target_date")
    op.drop_column("improvements", "effort")
    op.drop_column("improvements", "cluster_id")
