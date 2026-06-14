"""playbooks + cs_tasks (Fase 2 — Playbooks & Automação + fila de Tarefas de CS)

Duas tabelas novas (ver docs/FASE2_PLAYBOOKS_SPEC.md §2):

- playbooks: a regra (gatilho → ação), stateless. id, organization_id (FK CASCADE),
  name, description (NULL), enabled (DEFAULT true), trigger_type, trigger_config (JSONB),
  action_type, action_config (JSONB), created_at, updated_at.
- cs_tasks: a tarefa concreta na fila de CS. id, organization_id (FK CASCADE),
  contact_id (FK SET NULL), playbook_id (FK SET NULL), feedback_item_id (FK SET NULL),
  survey_response_id (FK SET NULL), title, reason, status (DEFAULT 'aberta'),
  priority (DEFAULT 'normal'), owner, due_at, snoozed_until, notes, meta (JSONB),
  dedup_key, created_at, updated_at, closed_at.

Índices: ix_playbooks_org; parcial ix_playbooks_org_trigger (org, trigger_type)
WHERE enabled; ix_cs_tasks_org_status_due; parcial ix_cs_tasks_org_open (org, status)
WHERE status='aberta'; ix_cs_tasks_contact; único uq_cs_tasks_dedup (org, dedup_key).

Os índices PARCIAIS (`postgresql_where`) são Postgres-only — moram só aqui, nunca no
__table_args__ dos models (senão quebram o create_all do SQLite nos testes).

playbooks é criada ANTES de cs_tasks (a FK cs_tasks.playbook_id referencia playbooks).

Revision ID: 20260613_playbooks_cs_tasks
Revises: 20260612c_improvements
Create Date: 2026-06-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260613_playbooks_cs_tasks"
down_revision: Union[str, None] = "20260612c_improvements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- playbooks (a regra) -------------------------------------------------
    op.create_table(
        "playbooks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("trigger_type", sa.String, nullable=False),
        sa.Column("trigger_config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("action_type", sa.String, nullable=False),
        sa.Column("action_config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_playbooks_org", "playbooks", ["organization_id"])
    # Parcial (PG-only): só playbooks ativos da org por gatilho — é o que o motor lê.
    op.create_index(
        "ix_playbooks_org_trigger",
        "playbooks",
        ["organization_id", "trigger_type"],
        postgresql_where=sa.text("enabled"),
    )

    # --- cs_tasks (a fila) ---------------------------------------------------
    op.create_table(
        "cs_tasks",
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
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "playbook_id",
            UUID(as_uuid=True),
            sa.ForeignKey("playbooks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "feedback_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("feedback_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "survey_response_id",
            UUID(as_uuid=True),
            sa.ForeignKey("survey_responses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="aberta"),
        sa.Column("priority", sa.String, nullable=False, server_default="normal"),
        sa.Column("owner", sa.String, nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("dedup_key", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        # Idempotência do motor: (org, dedup_key) único. Múltiplos NULL não colidem.
        sa.UniqueConstraint("organization_id", "dedup_key", name="uq_cs_tasks_dedup"),
    )
    op.create_index("ix_cs_tasks_org", "cs_tasks", ["organization_id"])
    op.create_index("ix_cs_tasks_org_status_due", "cs_tasks", ["organization_id", "status", "due_at"])
    op.create_index("ix_cs_tasks_contact", "cs_tasks", ["contact_id"])
    # Parcial (PG-only): a fila quente = tarefas abertas da org (o que a tela /tarefas mostra).
    op.create_index(
        "ix_cs_tasks_org_open",
        "cs_tasks",
        ["organization_id", "status"],
        postgresql_where=sa.text("status = 'aberta'"),
    )


def downgrade() -> None:
    op.drop_index("ix_cs_tasks_org_open", table_name="cs_tasks")
    op.drop_index("ix_cs_tasks_contact", table_name="cs_tasks")
    op.drop_index("ix_cs_tasks_org_status_due", table_name="cs_tasks")
    op.drop_index("ix_cs_tasks_org", table_name="cs_tasks")
    op.drop_table("cs_tasks")

    op.drop_index("ix_playbooks_org_trigger", table_name="playbooks")
    op.drop_index("ix_playbooks_org", table_name="playbooks")
    op.drop_table("playbooks")
