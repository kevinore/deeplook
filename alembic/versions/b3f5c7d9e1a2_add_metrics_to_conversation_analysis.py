"""add_metrics_to_conversation_analysis

Revision ID: b3f5c7d9e1a2
Revises: ec35d22dd679
Create Date: 2026-04-12 18:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3f5c7d9e1a2'
down_revision: Union[str, None] = 'ec35d22dd679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_analysis', sa.Column('avg_response_time_seconds', sa.Float(), nullable=True))
    op.add_column('conversation_analysis', sa.Column('median_response_time_seconds', sa.Float(), nullable=True))
    op.add_column('conversation_analysis', sa.Column('p95_response_time_seconds', sa.Float(), nullable=True))
    op.add_column('conversation_analysis', sa.Column('unanswered_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('conversation_analysis', sa.Column('total_messages', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('conversation_analysis', sa.Column('inbound_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('conversation_analysis', sa.Column('outbound_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('conversation_analysis', sa.Column('duration_minutes', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'duration_minutes')
    op.drop_column('conversation_analysis', 'outbound_count')
    op.drop_column('conversation_analysis', 'inbound_count')
    op.drop_column('conversation_analysis', 'total_messages')
    op.drop_column('conversation_analysis', 'unanswered_count')
    op.drop_column('conversation_analysis', 'p95_response_time_seconds')
    op.drop_column('conversation_analysis', 'median_response_time_seconds')
    op.drop_column('conversation_analysis', 'avg_response_time_seconds')
