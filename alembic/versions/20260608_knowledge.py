"""knowledge_chunks — base de conhecimento para RAG (pgvector)

Tabela do corpus por organização: cada linha é um trecho (seção) de um
documento, com seu embedding de 384 dims (all-MiniLM-L6-v2). O retriever busca
por similaridade de cosseno (operador <=> do pgvector).

Revision ID: 20260608_knowledge
Revises: 20260607_ai_fields
Create Date: 2026-06-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "20260608_knowledge"
down_revision: Union[str, None] = "20260607_ai_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_chunks_org", "knowledge_chunks", ["organization_id"])

    # embedding fica fora do ORM (ver app/models/knowledge.py) — coluna nativa pgvector.
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(384)")
    # HNSW por cosseno: bom recall sem precisar de dados pré-existentes (≠ ivfflat).
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_org", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
