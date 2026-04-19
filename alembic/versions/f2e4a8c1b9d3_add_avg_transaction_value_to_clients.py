"""add_avg_transaction_value_to_clients

Revision ID: f2e4a8c1b9d3
Revises: d9f3b7e2c4a8
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2e4a8c1b9d3'
down_revision: Union[str, None] = 'd9f3b7e2c4a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('average_transaction_value', sa.Float(), nullable=True))
    op.add_column('conversation_analysis', sa.Column('customer_questions', postgresql.JSONB(), nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'customer_questions')
    op.drop_column('clients', 'average_transaction_value')
