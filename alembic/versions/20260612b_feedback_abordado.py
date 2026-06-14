"""feedback_items.abordado + abordado_em (CRUD de feedbacks — flag "abordado")

Marca se o operador (Felipe) JÁ ABORDOU o cliente sobre o feedback — separado do
`action_status` (que é o estágio do tratamento interno) e da IA. Quando o feedback
é marcado como abordado, `abordado_em` registra o instante (preenchido na API).

- abordado: BOOLEAN NOT NULL DEFAULT false (server_default => linhas existentes
  nascem `false`; aditivo e seguro p/ a tabela já populada).
- abordado_em: TIMESTAMPTZ NULL — quando o cliente foi abordado (NULL = ainda não).

Revision ID: 20260612b_feedback_abordado
Revises: 20260612_feedback_action
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260612b_feedback_abordado"
down_revision: Union[str, None] = "20260612_feedback_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "feedback_items",
        sa.Column("abordado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "feedback_items",
        sa.Column("abordado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feedback_items", "abordado_em")
    op.drop_column("feedback_items", "abordado")
