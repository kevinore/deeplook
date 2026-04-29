"""add_last_session_active_at_to_whatsapp_connections

Revision ID: f3a8b2c5d9e1
Revises: e7c2a4d6f1b8
Create Date: 2026-04-29 18:00:00.000000

Adds `last_session_active_at` column used by the WAHA keepalive job to keep
WhatsApp's 14-day device-link timeout from killing dormant sessions.

The keepalive job pings each connection every ~7 days to reset WhatsApp's
inactivity counter, even when the user's plan only generates a report every
15 or 30 days. Updated by:
  - successful sync (whatsapp_sync_service.run_waha_sync_job)
  - keepalive  (whatsapp_keepalive.run_keepalive)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a8b2c5d9e1'
down_revision: Union[str, None] = 'e7c2a4d6f1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'whatsapp_connections',
        sa.Column('last_session_active_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from last_sync_at so existing connections don't trigger an
    # immediate keepalive on the very first run after deploy.
    op.execute(
        "UPDATE whatsapp_connections "
        "SET last_session_active_at = last_sync_at "
        "WHERE last_sync_at IS NOT NULL"
    )
    op.create_index(
        'ix_whatsapp_connections_keepalive',
        'whatsapp_connections',
        ['last_session_active_at', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_whatsapp_connections_keepalive', table_name='whatsapp_connections')
    op.drop_column('whatsapp_connections', 'last_session_active_at')
