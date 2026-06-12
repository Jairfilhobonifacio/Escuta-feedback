"""messages (transcript) + contacts.needs_human_handoff/handoff_at

Base do chatbot conversacional (memória da conversa) e do hand-off humano.

Revision ID: 20260610c_chatbot
Revises: 20260610b_feedback_items
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260610c_chatbot"
down_revision: Union[str, None] = "20260610b_feedback_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("survey_response_id", UUID(as_uuid=True), sa.ForeignKey("survey_responses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("channel_msg_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_organization_id", "messages", ["organization_id"])
    op.create_index("ix_messages_contact_id", "messages", ["contact_id"])
    op.create_index("ix_message_org_contact_time", "messages", ["organization_id", "contact_id", "created_at"])
    op.create_index("ix_message_contact_time", "messages", ["contact_id", "created_at"])

    op.add_column("contacts", sa.Column("needs_human_handoff", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("contacts", sa.Column("handoff_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "handoff_at")
    op.drop_column("contacts", "needs_human_handoff")
    op.drop_table("messages")
