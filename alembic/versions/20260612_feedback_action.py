"""feedback_items.action_status + action_note (Central de Monitoramento)

Estado da AÇÃO tomada sobre cada sinal de feedback (workflow do Felipe), separado
do enriquecimento por IA. Permite triar o feed: novo -> em_analise -> planejado ->
resolvido (ou descartado).

- action_status: VARCHAR NOT NULL DEFAULT 'novo' (server_default => linhas
  existentes nascem 'novo'; aditivo e seguro p/ a tabela já populada).
  Valores válidos (validados na API, não por CHECK no banco — vocabulário pode
  crescer): novo | em_analise | planejado | resolvido | descartado.
- action_note: TEXT NULL — nota interna do operador sobre a ação tomada.

Revision ID: 20260612_feedback_action
Revises: 20260610c_chatbot
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_feedback_action"
down_revision: Union[str, None] = "20260610c_chatbot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "feedback_items",
        sa.Column("action_status", sa.String(), nullable=False, server_default="novo"),
    )
    op.add_column(
        "feedback_items",
        sa.Column("action_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feedback_items", "action_note")
    op.drop_column("feedback_items", "action_status")
