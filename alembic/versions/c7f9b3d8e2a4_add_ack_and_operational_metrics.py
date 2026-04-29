"""add_ack_and_operational_metrics

Adds deterministic WAHA-derived metrics to conversation_analysis:

  • trailing_inbound_messages — diagnostic: # of consecutive customer
    messages at the end of a chat that went unanswered.
  • delivery_rate, read_rate    — % outbound delivered / read by the customer.
  • is_ghosted                  — last business message READ but no reply.
  • last_business_msg_ack       — WAHA ack code of most recent outbound.
  • operational_coverage_score  — % of in-hours customer messages answered
    within 1 h. Replaces the hardcoded 50 in the health-score formula.
  • out_of_hours_inbound_pct    — context: % of inbound that arrived outside
    business hours.
  • wa_unread_count             — chat-level unreadCount captured from WAHA.
  • wa_is_muted, wa_is_archived — chat-level flags so we can exclude
    intentionally silenced chats from "needs response" calculations.

Note: existing `unanswered_count` rows are NOT migrated — they used to mean
"# of trailing unanswered messages" and now mean "0|1 conversation
unanswered". For a clean cutover, the migration is forward-compatible and
older job data simply carries the old semantic. New jobs use the new one.

Revision ID: c7f9b3d8e2a4
Revises: 0f0cc75591ac
Create Date: 2026-04-28 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7f9b3d8e2a4'
down_revision: Union[str, None] = '0f0cc75591ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = [
    sa.Column('trailing_inbound_messages', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('delivery_rate', sa.Float(), nullable=True),
    sa.Column('read_rate', sa.Float(), nullable=True),
    sa.Column('is_ghosted', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('last_business_msg_ack', sa.Integer(), nullable=True),
    sa.Column('operational_coverage_score', sa.Float(), nullable=True),
    sa.Column('out_of_hours_inbound_pct', sa.Float(), nullable=True),
    sa.Column('wa_unread_count', sa.Integer(), nullable=True),
    sa.Column('wa_is_muted', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('wa_is_archived', sa.Boolean(), nullable=False, server_default=sa.false()),
]


def upgrade() -> None:
    for col in _NEW_COLUMNS:
        op.add_column('conversation_analysis', col)


def downgrade() -> None:
    for col in reversed(_NEW_COLUMNS):
        op.drop_column('conversation_analysis', col.name)
