"""add_token_split_columns

Revision ID: a3c7f1d2e8b5
Revises: f2e4a8c1b9d3
Create Date: 2026-04-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c7f1d2e8b5'
down_revision: Union[str, None] = 'f2e4a8c1b9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_jobs', sa.Column('total_tokens_input', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('analysis_jobs', sa.Column('total_tokens_output', sa.Integer(), nullable=False, server_default='0'))

    op.add_column('conversation_analysis', sa.Column('tokens_input', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('conversation_analysis', sa.Column('tokens_output', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('conversation_analysis', 'tokens_output')
    op.drop_column('conversation_analysis', 'tokens_input')
    op.drop_column('analysis_jobs', 'total_tokens_output')
    op.drop_column('analysis_jobs', 'total_tokens_input')
