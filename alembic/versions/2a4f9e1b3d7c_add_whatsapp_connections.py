"""add_whatsapp_connections

Revision ID: 2a4f9e1b3d7c
Revises: c1e5f8a2b3d7
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '2a4f9e1b3d7c'
down_revision: Union[str, None] = 'c1e5f8a2b3d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_connections',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('client_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('waha_session_name', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='STOPPED'),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('push_name', sa.String(255), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('analysis_jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sync_frequency', sa.String(20), nullable=False, server_default='monthly'),
        sa.Column('next_scheduled_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_reconnect_email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_whatsapp_connections_next_sync', 'whatsapp_connections', ['next_scheduled_sync_at', 'status'])


def downgrade() -> None:
    op.drop_index('ix_whatsapp_connections_next_sync', table_name='whatsapp_connections')
    op.drop_table('whatsapp_connections')
