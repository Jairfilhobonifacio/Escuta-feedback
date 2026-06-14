"""improvements (roadmap) + feedback_items.improvement_id ("Fechar o loop")

Tabela `improvements`: melhoria do produto que nasce de feedbacks. O operador
agrupa feedbacks numa melhoria, acompanha o status (ideia → entregue) e, ao
entregar, pode avisar os clientes que pediram ("você pediu, a gente fez").

- improvements: id, organization_id (FK CASCADE), title, description (NULL),
  status (DEFAULT 'ideia'), created_at, delivered_at (NULL), notified_at (NULL).
- feedback_items.improvement_id: UUID FK NULL → improvements (ON DELETE SET NULL).
  Aditivo e seguro p/ a tabela já populada (linhas existentes nascem NULL = "sem
  melhoria"). Um feedback pertence a no máximo UMA melhoria.

A criação da tabela vem ANTES do add_column (a FK referencia improvements).

Revision ID: 20260612c_improvements
Revises: 20260612b_feedback_abordado
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260612c_improvements"
down_revision: Union[str, None] = "20260612b_feedback_abordado"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "improvements",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="ideia"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_improvements_organization_id", "improvements", ["organization_id"])
    op.create_index("ix_improvement_org_status", "improvements", ["organization_id", "status"])

    # Vínculo feedback → melhoria (aditivo, NULL p/ linhas existentes).
    op.add_column(
        "feedback_items",
        sa.Column("improvement_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_feedback_items_improvement_id", "feedback_items", ["improvement_id"]
    )
    op.create_foreign_key(
        "fk_feedback_items_improvement_id",
        "feedback_items",
        "improvements",
        ["improvement_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_feedback_items_improvement_id", "feedback_items", type_="foreignkey")
    op.drop_index("ix_feedback_items_improvement_id", table_name="feedback_items")
    op.drop_column("feedback_items", "improvement_id")
    op.drop_index("ix_improvement_org_status", table_name="improvements")
    op.drop_index("ix_improvements_organization_id", table_name="improvements")
    op.drop_table("improvements")
