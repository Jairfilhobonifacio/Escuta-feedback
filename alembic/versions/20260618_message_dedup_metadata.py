"""message_dedup_metadata — msg_metadata (JSONB) + índice único PARCIAL p/ dedup atômico

Fase 1 (webhook + dedup): torna o transcript idempotente NO BANCO, não só por
SELECT-then-INSERT (que corre risco em retry concorrente do gateway). Adiciona à
tabela `messages`:

- `msg_metadata JSONB NULL` — saco de metadados livres da mensagem (schema em
  app/schemas/messages.py). Aditivo e seguro p/ linhas existentes (nascem NULL).
- índice único PARCIAL `uq_messages_org_channel_msg_id (organization_id,
  channel_msg_id) WHERE channel_msg_id IS NOT NULL` — o MESMO turno do WAHA só
  entra UMA vez por org. Parcial: outbound do bot (sem channel_msg_id) não
  colide. Com ele, o webhook pode fazer insert atômico e absorver a duplicata
  via IntegrityError (try/except + rollback) em vez de quebrar.

`channel_msg_id` hoje é nullable e SEM unique (ver app/models/survey.py) — esta
migration introduz o unique parcial. O CREATE INDEX é CONCURRENTLY-friendly? Não:
para portabilidade (e porque roda dentro da transação da migration) usamos o
CREATE INDEX comum; aplicar no piloto exige OK do dono (a base pode ter duplicatas
pré-existentes que precisam ser deduplicadas antes — ver nota abaixo).

NOTA OPERACIONAL (não executar aqui): se a tabela já tiver pares
(organization_id, channel_msg_id) duplicados, o CREATE INDEX UNIQUE falha. Antes
de aplicar no piloto, deduplicar mantendo a linha mais antiga, p.ex.:
    DELETE FROM messages a USING messages b
    WHERE a.ctid < b.ctid
      AND a.organization_id = b.organization_id
      AND a.channel_msg_id = b.channel_msg_id
      AND a.channel_msg_id IS NOT NULL;

Revision ID: 20260618_message_dedup_metadata
Revises: 20260614c_feedback_assignee
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260618_message_dedup_metadata"
down_revision: Union[str, None] = "20260614c_feedback_assignee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # msg_metadata: JSONB no Postgres (variante explícita), nullable e aditivo.
    op.add_column(
        "messages",
        sa.Column("msg_metadata", JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Índice único PARCIAL — dedup atômico do turno por org (Postgres).
    op.create_index(
        "uq_messages_org_channel_msg_id",
        "messages",
        ["organization_id", "channel_msg_id"],
        unique=True,
        postgresql_where=sa.text("channel_msg_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_org_channel_msg_id", table_name="messages")
    op.drop_column("messages", "msg_metadata")
