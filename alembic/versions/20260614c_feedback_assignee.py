"""feedback_assignee — responsável + roteamento por time (Camada 2 — Board de Gestão)

Ver docs/BOARD_GESTAO_SPEC.md §1.

Adiciona à tabela `feedback_items` (tudo aditivo/portável — sem pgvector, roda no
SQLite dos testes):
- `assignee VARCHAR NULL` — quem do time cuida do feedback (slug/email; sem tabela
  de users, igual `cs_tasks.owner`).
- `team_tag VARCHAR NULL` — roteamento por time ('produto'/'suporte'/'comercial'/'cs').
Índice `ix_feedback_items_assignee (organization_id, assignee)` p/ o Board filtrar/
agrupar por responsável dentro da org.

Revision ID: 20260614c_feedback_assignee
Revises: 20260614b_roadmap_links
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260614c_feedback_assignee"
down_revision: Union[str, None] = "20260614b_roadmap_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feedback_items", sa.Column("assignee", sa.String, nullable=True))
    op.add_column("feedback_items", sa.Column("team_tag", sa.String, nullable=True))
    op.create_index(
        "ix_feedback_items_assignee",
        "feedback_items",
        ["organization_id", "assignee"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_items_assignee", table_name="feedback_items")
    op.drop_column("feedback_items", "team_tag")
    op.drop_column("feedback_items", "assignee")
