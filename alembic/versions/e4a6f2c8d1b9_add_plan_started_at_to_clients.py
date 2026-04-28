"""add_plan_started_at_to_clients

Revision ID: e4a6f2c8d1b9
Revises: 2a4f9e1b3d7c
Create Date: 2026-04-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e4a6f2c8d1b9'
down_revision: Union[str, None] = '2a4f9e1b3d7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('plan_started_at', sa.DateTime(timezone=True), nullable=True))
    # Backfill existing rows: anchor their billing cycle to when the client was created
    op.execute("UPDATE clients SET plan_started_at = created_at WHERE plan_started_at IS NULL")


def downgrade() -> None:
    op.drop_column('clients', 'plan_started_at')
