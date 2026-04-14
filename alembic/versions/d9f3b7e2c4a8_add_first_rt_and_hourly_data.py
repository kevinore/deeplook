"""add_first_rt_and_hourly_data

Revision ID: d9f3b7e2c4a8
Revises: b3f5c7d9e1a2
Create Date: 2026-04-12 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd9f3b7e2c4a8'
down_revision: Union[str, None] = 'b3f5c7d9e1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_analysis', sa.Column('first_response_time_seconds', sa.Float(), nullable=True))
    op.add_column('conversation_analysis', sa.Column('response_time_by_hour', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'response_time_by_hour')
    op.drop_column('conversation_analysis', 'first_response_time_seconds')
