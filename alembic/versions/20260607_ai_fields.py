"""survey_responses: campos de enriquecimento por IA (SurveyBrain)

sentiment/themes/ai_meta são preenchidos pela classificação multi-eixo no
fechamento da response (Groq). Nullable de ponta a ponta: LLM desligado ou
indisponível = colunas ficam NULL e nada mais muda.

Revision ID: 20260607_ai_fields
Revises: 20260607_trigger_event
Create Date: 2026-06-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260607_ai_fields"
down_revision: Union[str, None] = "20260607_trigger_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("survey_responses", sa.Column("sentiment", sa.String, nullable=True))
    op.add_column("survey_responses", sa.Column("themes", JSONB, nullable=True))
    op.add_column("survey_responses", sa.Column("ai_meta", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("survey_responses", "ai_meta")
    op.drop_column("survey_responses", "themes")
    op.drop_column("survey_responses", "sentiment")
