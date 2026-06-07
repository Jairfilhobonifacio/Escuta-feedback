"""surveys.trigger_event — disparo automático por evento de ciclo de vida

Surveys com trigger_event preenchido são disparadas pelo endpoint
/api/events/<fonte> quando o evento correspondente chega (ex.: exit survey
em 'subscription_cancelled'). NULL mantém o comportamento atual (manual).

Revision ID: 20260607_trigger_event
Revises: 20260605_initial
Create Date: 2026-06-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260607_trigger_event"
down_revision: Union[str, None] = "20260605_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surveys", sa.Column("trigger_event", sa.String, nullable=True))
    op.create_index("ix_surveys_org_trigger", "surveys", ["organization_id", "trigger_event"])


def downgrade() -> None:
    op.drop_index("ix_surveys_org_trigger", table_name="surveys")
    op.drop_column("surveys", "trigger_event")
