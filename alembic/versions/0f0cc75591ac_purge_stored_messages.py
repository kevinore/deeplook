"""Drop messages table — raw WhatsApp text content is no longer stored.
The analysis pipeline now passes NormalizedConversation objects in-memory
directly to the AI worker. Message text is never persisted to the database.

Revision ID: 0f0cc75591ac
Revises: b3c5e8f1a2d4
Create Date: 2026-04-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0f0cc75591ac"
down_revision = "b3c5e8f1a2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_messages_conversation_source", table_name="messages")
    op.drop_index("ix_messages_conversation_timestamp", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")


def downgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("sender_phone", sa.String(50), nullable=True),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("message_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
