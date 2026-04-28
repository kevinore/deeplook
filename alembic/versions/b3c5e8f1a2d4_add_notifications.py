"""add_notifications

Revision ID: b3c5e8f1a2d4
Revises: a1b2c3d4e5f6
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b3c5e8f1a2d4'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('is_read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('extra_data', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['analysis_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_client_created', 'notifications', ['client_id', 'created_at'])
    op.create_index('ix_notifications_client_unread', 'notifications', ['client_id', 'is_read'])


def downgrade() -> None:
    op.drop_index('ix_notifications_client_unread', table_name='notifications')
    op.drop_index('ix_notifications_client_created', table_name='notifications')
    op.drop_table('notifications')
