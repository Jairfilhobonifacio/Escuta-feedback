"""survey_responses.source + surveys.ingest_mode (NPS in-app ingest)

Dois campos para o modo "ingest" (espelho do NPS in-app da Bizzu):
- survey_responses.source: 'whatsapp' (disparada+respondida no WA) | 'in_app'
  (ingerida já respondida, sem disparo).
- surveys.ingest_mode: True => o POST /api/events/* registra+classifica a
  resposta e NÃO dispara WhatsApp.

Ambos com server_default => safe para tabelas com dados (linhas existentes
nascem 'whatsapp' / false).

Revision ID: 20260610_nps_ingest
Revises: 20260608_knowledge
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260610_nps_ingest"
down_revision: Union[str, None] = "20260608_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "survey_responses",
        sa.Column("source", sa.String(), nullable=False, server_default="whatsapp"),
    )
    op.add_column(
        "surveys",
        sa.Column("ingest_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("surveys", "ingest_mode")
    op.drop_column("survey_responses", "source")
