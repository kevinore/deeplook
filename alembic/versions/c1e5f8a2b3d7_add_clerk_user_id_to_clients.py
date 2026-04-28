"""add_clerk_user_id_to_clients

Revision ID: c1e5f8a2b3d7
Revises: a3c7f1d2e8b5
Create Date: 2026-04-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1e5f8a2b3d7'
down_revision: Union[str, None] = 'a3c7f1d2e8b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('clerk_user_id', sa.String(255), nullable=True))
    op.create_index('ix_clients_clerk_user_id', 'clients', ['clerk_user_id'])


def downgrade() -> None:
    op.drop_index('ix_clients_clerk_user_id', table_name='clients')
    op.drop_column('clients', 'clerk_user_id')
