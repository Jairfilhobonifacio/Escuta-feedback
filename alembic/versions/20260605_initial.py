"""initial — organizations, contacts + survey tables (Fase 0)

Primeira migration do repo (down_revision = None). Cria o subconjunto mínimo
para o tracer bullet de NPS. Convenção espelha o Nexus (YYYYMMDD_desc.py).

Revision ID: 20260605_initial
Revises:
Create Date: 2026-06-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "20260605_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID_PK = dict(server_default=sa.text("gen_random_uuid()"), primary_key=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("settings", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=True),
        sa.Column("profile_data", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("opt_in", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "phone", name="uq_contact_org_phone"),
    )
    op.create_index("ix_contacts_org", "contacts", ["organization_id"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])

    op.create_table(
        "surveys",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("questions", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_survey_org_name"),
    )
    op.create_index("ix_surveys_org", "surveys", ["organization_id"])

    op.create_table(
        "survey_runs",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("survey_id", UUID(as_uuid=True), sa.ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String, server_default=sa.text("'manual'")),
        sa.Column("status", sa.String, server_default=sa.text("'running'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_survey_runs_survey", "survey_runs", ["survey_id"])
    op.create_index("ix_survey_runs_org", "survey_runs", ["organization_id"])

    op.create_table(
        "survey_responses",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("survey_run_id", UUID(as_uuid=True), sa.ForeignKey("survey_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String, server_default=sa.text("'sent'"), nullable=False),
        sa.Column("answer_score", sa.Integer, nullable=True),
        sa.Column("nps_bucket", sa.String, nullable=True),
        sa.Column("answer_text", sa.Text, nullable=True),
        sa.Column("channel_msg_id", sa.String, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("survey_run_id", "contact_id", name="uq_survey_response_run_contact"),
    )
    op.create_index("ix_survey_response_run", "survey_responses", ["survey_run_id"])
    op.create_index("ix_survey_response_contact", "survey_responses", ["contact_id"])
    op.create_index(
        "ix_survey_response_org_contact_status",
        "survey_responses",
        ["organization_id", "contact_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("survey_responses")
    op.drop_table("survey_runs")
    op.drop_table("surveys")
    op.drop_table("contacts")
    op.drop_table("organizations")
