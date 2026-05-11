"""add connections_only to payment_sessions

Revision ID: m4d5e6f7g8h9
Revises: l3c4d5e6f7g8
Create Date: 2026-05-10

"""
from alembic import op
import sqlalchemy as sa

revision = 'm4d5e6f7g8h9'
down_revision = 'l3c4d5e6f7g8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('payment_sessions', sa.Column('connections_only', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('payment_sessions', 'connections_only')
