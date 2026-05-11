"""add_multi_account_whatsapp

Revision ID: j1a2b3c4d5e6
Revises: i6f2d9b5e7c8
Create Date: 2026-05-09 10:00:00.000000

Allow multiple WhatsApp connections per client:
- Drop UNIQUE on whatsapp_connections.client_id
- Add display_name, share_token, share_token_expires_at columns
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = 'j1a2b3c4d5e6'
down_revision: Union[str, None] = 'i6f2d9b5e7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_connections', sa.Column('display_name', sa.String(100), nullable=True))
    op.add_column('whatsapp_connections', sa.Column('share_token', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('whatsapp_connections', sa.Column('share_token_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Allow multiple connections per client
    op.drop_constraint('whatsapp_connections_client_id_key', 'whatsapp_connections', type_='unique')

    # PostgreSQL excludes NULLs from unique indexes automatically — safe for nullable column
    op.create_index('ix_whatsapp_connections_share_token', 'whatsapp_connections', ['share_token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_whatsapp_connections_share_token', 'whatsapp_connections')
    op.create_unique_constraint('whatsapp_connections_client_id_key', 'whatsapp_connections', ['client_id'])
    op.drop_column('whatsapp_connections', 'share_token_expires_at')
    op.drop_column('whatsapp_connections', 'share_token')
    op.drop_column('whatsapp_connections', 'display_name')
