"""add client_relationship to conversation_analysis

Revision ID: o6f7g8h9i0j1
Revises: n5e6f7g8h9i0
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'o6f7g8h9i0j1'
down_revision = 'n5e6f7g8h9i0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversation_analysis',
        sa.Column('client_relationship', sa.String(20), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('client_relationship_source', sa.String(20), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('client_relationship_signals', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'client_relationship_signals')
    op.drop_column('conversation_analysis', 'client_relationship_source')
    op.drop_column('conversation_analysis', 'client_relationship')
