"""add avg_response_time_bh_seconds to conversation_analysis

Revision ID: n5e6f7g8h9i0
Revises: m4d5e6f7g8h9
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'n5e6f7g8h9i0'
down_revision = 'm4d5e6f7g8h9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversation_analysis',
        sa.Column('avg_response_time_bh_seconds', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'avg_response_time_bh_seconds')
