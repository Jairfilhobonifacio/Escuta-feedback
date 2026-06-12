"""feedback_items — Mega Central de Dados (sinais unificados de qualquer fonte)

Tabela genérica que unifica feedback de NPS in-app, churn, tickets, reports,
solicitações, etc. — ingeridos por pull (API de Clientes) ou push (eventos do
backend). Base da Visão 360 do cliente + clustering (Fase 2).

Revision ID: 20260610b_feedback_items
Revises: 20260610_nps_ingest
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "20260610b_feedback_items"
down_revision: Union[str, None] = "20260610_nps_ingest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("external_id", sa.String, nullable=True),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("nps_bucket", sa.String, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("sentiment", sa.String, nullable=True),
        sa.Column("themes", JSONB, nullable=True),
        sa.Column("ai_meta", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_items_organization_id", "feedback_items", ["organization_id"])
    op.create_index("ix_feedback_items_contact_id", "feedback_items", ["contact_id"])
    op.create_index(
        "ix_feedback_org_contact_occurred",
        "feedback_items",
        ["organization_id", "contact_id", "occurred_at"],
    )
    op.create_unique_constraint(
        "uq_feedback_org_external", "feedback_items", ["organization_id", "external_id"]
    )


def downgrade() -> None:
    op.drop_table("feedback_items")
