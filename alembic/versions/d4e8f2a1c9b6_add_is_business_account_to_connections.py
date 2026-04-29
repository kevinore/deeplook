"""add_is_business_account_to_connections

Revision ID: d4e8f2a1c9b6
Revises: c7f9b3d8e2a4
Create Date: 2026-04-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e8f2a1c9b6'
down_revision: Union[str, None] = 'c7f9b3d8e2a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'whatsapp_connections',
        sa.Column('is_business_account', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('whatsapp_connections', 'is_business_account')
