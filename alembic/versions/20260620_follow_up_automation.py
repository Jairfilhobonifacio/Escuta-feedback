"""follow_up_automation — follow_up_at + auto-reopen on inbound (Níveis 1-2)

Fase 1 (encadeada após 20260618b_roadmap_cross_links).

Adiciona à tabela `feedback_items`:
- `follow_up_at TIMESTAMP NULL` — instante em que o feedback deve ser REABORDADO.
  NULL = sem follow-up; "vencido" = follow_up_at <= now (a fila do operador filtra).

DEFENSIVA e IDEMPOTENTE no estilo das migrations existentes (20260618b): inspeciona
o banco em runtime e só adiciona a coluna / o índice de apoio onde faltarem. Re-rodar
é no-op. O auto-reabrir no inbound (cliente respondeu → feedbacks em status terminal/
aguardando voltam p/ 'a_abordar' + follow_up_at=NULL) é lógica de aplicação (webhook),
não precisa de schema novo além desta coluna.

Aplicar no piloto exige OK do dono (guarda da tarefa) — aqui só ESCREVEMOS o arquivo.

Revision ID: 20260620_follow_up_automation
Revises: 20260618b_roadmap_cross_links
Create Date: 2026-06-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260620_follow_up_automation"
down_revision: Union[str, None] = "20260618b_roadmap_cross_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "feedback_items"
_COLUMN = "follow_up_at"
_INDEX = "ix_feedback_items_follow_up_at"


def _existing_columns(inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:  # noqa: BLE001 — tabela ausente em algum ambiente: trata como vazia.
        return set()


def _existing_indexes(inspector, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in inspector.get_indexes(table)}
    except Exception:  # noqa: BLE001
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cols = _existing_columns(inspector, _TABLE)
    if not cols:
        # Tabela não existe neste ambiente — nada a fazer (migrations anteriores criam).
        return

    if _COLUMN not in cols:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True),
        )

    # Índice de apoio à fila de follow-ups vencidos (filtra por org + follow_up_at).
    if _INDEX not in _existing_indexes(inspector, _TABLE):
        op.create_index(_INDEX, _TABLE, ["organization_id", _COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _INDEX in _existing_indexes(inspector, _TABLE):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _existing_columns(inspector, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
