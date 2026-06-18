"""roadmap_cross_links — garante os vínculos cruzados improvement_id (idempotente)

Fase 1 (encadeada após 20260618_message_dedup_metadata).

Objetivo do handoff: garantir que as tabelas de cluster/feedback tenham a coluna
`improvement_id` (FK → improvements, ON DELETE SET NULL) para fechar o loop
dor→melhoria.

ESTADO REAL DO SCHEMA (conferido nos models + migrations anteriores):
- `feedback_items.improvement_id`   já EXISTE (migration 20260612c_improvements:
  add_column + FK fk_feedback_items_improvement_id + ix_feedback_items_improvement_id).
- `feedback_clusters.improvement_id` já EXISTE (migration 20260614_feedback_clusters:
  criada junto da tabela + ix_feedback_clusters_improvement).

Portanto NÃO há coluna nova a adicionar no schema atual. Esta migration é, por
isso, DEFENSIVA e IDEMPOTENTE: inspeciona o banco em runtime e só cria a coluna
(+ índice + FK) onde ela faltar. No piloto atual ela é um no-op; o valor é manter
a cadeia consistente e ser auto-curativa caso algum ambiente esteja atrás (a
coluna some/nunca foi aplicada).

Aplicar no piloto exige OK do dono (guarda da tarefa) — aqui só ESCREVEMOS.

Revision ID: 20260618b_roadmap_cross_links
Revises: 20260618_message_dedup_metadata
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260618b_roadmap_cross_links"
down_revision: Union[str, None] = "20260618_message_dedup_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, nome do índice de apoio) — a coluna é sempre `improvement_id`.
_TARGETS = (
    ("feedback_items", "ix_feedback_items_improvement_id"),
    ("feedback_clusters", "ix_feedback_clusters_improvement"),
)


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

    for table, index_name in _TARGETS:
        cols = _existing_columns(inspector, table)
        if not cols:
            # Tabela não existe neste ambiente — nada a fazer (migrations anteriores
            # cuidam da criação; não é papel desta migration recriá-la).
            continue
        if "improvement_id" not in cols:
            # Coluna faltando: adiciona com FK SET NULL (auto-cura ambientes atrás).
            op.add_column(
                table,
                sa.Column(
                    "improvement_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("improvements.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        # Garante o índice de apoio (no-op se já existe).
        if index_name not in _existing_indexes(inspector, table):
            op.create_index(index_name, table, ["improvement_id"])


def downgrade() -> None:
    # Idempotente/no-op por design: não removemos colunas que esta migration NÃO
    # criou no schema atual (improvement_id pertence às migrations 20260612c /
    # 20260614). O downgrade não desfaz as garantias auto-curativas — deixá-las é
    # seguro e evita derrubar colunas que outras migrations consideram suas.
    pass
