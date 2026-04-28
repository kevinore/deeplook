"""add_plan_expires_at_to_clients

Revision ID: a1b2c3d4e5f6
Revises: f1a3c9d2e7b8
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a3c9d2e7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('plan_expires_at', sa.DateTime(timezone=True), nullable=True))
    # Backfill: existing active paid plans expire 30 days after they started
    op.execute("""
        UPDATE clients
        SET plan_expires_at = plan_started_at + INTERVAL '30 days'
        WHERE plan != 'free'
          AND plan_started_at IS NOT NULL
          AND plan_expires_at IS NULL
    """)


def downgrade() -> None:
    op.drop_column('clients', 'plan_expires_at')
