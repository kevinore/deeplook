"""add connections_limit to clients and extra_connections to payment_sessions

Revision ID: l3c4d5e6f7g8
Revises: k2b3c4d5e6f7
Create Date: 2026-05-10

"""
from alembic import op
import sqlalchemy as sa

revision = 'l3c4d5e6f7g8'
down_revision = 'k2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('connections_limit', sa.Integer(), nullable=True))
    op.add_column('payment_sessions', sa.Column('extra_connections', sa.Integer(), server_default='0', nullable=False))

    # Grandfather existing paid/trial clients: connections_limit = MAX(plan default, actual count)
    op.execute("""
        UPDATE clients
        SET connections_limit = GREATEST(
            CASE plan
                WHEN 'basic'      THEN 1
                WHEN 'plus'       THEN 1
                WHEN 'enterprise' THEN 2
                ELSE 0
            END,
            (SELECT COUNT(*) FROM whatsapp_connections WHERE client_id = clients.id)
        )
        WHERE subscription_status IN ('active', 'trial')
    """)


def downgrade() -> None:
    op.drop_column('payment_sessions', 'extra_connections')
    op.drop_column('clients', 'connections_limit')
