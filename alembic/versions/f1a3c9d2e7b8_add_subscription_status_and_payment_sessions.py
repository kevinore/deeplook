"""add_subscription_status_and_payment_sessions

Revision ID: f1a3c9d2e7b8
Revises: e4a6f2c8d1b9
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f1a3c9d2e7b8'
down_revision: Union[str, None] = 'e4a6f2c8d1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add subscription_status to clients
    op.add_column('clients', sa.Column('subscription_status', sa.String(30), nullable=False, server_default='inactive'))

    # Create payment_sessions table
    op.create_table(
        'payment_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('client_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan', sa.String(50), nullable=False),
        sa.Column('amount_in_cents', sa.Integer, nullable=False),
        sa.Column('reference', sa.String(200), nullable=False, unique=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('wompi_transaction_id', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_payment_sessions_reference', 'payment_sessions', ['reference'])
    op.create_index('ix_payment_sessions_client_id', 'payment_sessions', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_payment_sessions_client_id', table_name='payment_sessions')
    op.drop_index('ix_payment_sessions_reference', table_name='payment_sessions')
    op.drop_table('payment_sessions')
    op.drop_column('clients', 'subscription_status')
