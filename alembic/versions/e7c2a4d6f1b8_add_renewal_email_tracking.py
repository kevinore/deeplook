"""add_renewal_email_tracking_to_clients

Revision ID: e7c2a4d6f1b8
Revises: d4e8f2a1c9b6
Create Date: 2026-04-29 17:00:00.000000

Adds two columns to the `clients` table to dedupe renewal-reminder emails:
- last_renewal_email_sent_at  TIMESTAMP  → most recent reminder send time
- last_renewal_email_stage    VARCHAR(10) → '7d' | '3d' | '1d' (most recent stage)

The scheduler's daily renewal-check job uses these to ensure each stage is
only emailed once per renewal cycle.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7c2a4d6f1b8'
down_revision: Union[str, None] = 'd4e8f2a1c9b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('last_renewal_email_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('clients', sa.Column('last_renewal_email_stage', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'last_renewal_email_stage')
    op.drop_column('clients', 'last_renewal_email_sent_at')
