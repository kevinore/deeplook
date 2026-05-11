"""add_connection_id_to_analysis_jobs

Revision ID: k2b3c4d5e6f7
Revises: j1a2b3c4d5e6
Create Date: 2026-05-09 10:05:00.000000

Tag each analysis_job with the WhatsApp connection that generated it (nullable —
.txt uploads remain NULL; WAHA-originated jobs carry the connection_id).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = 'k2b3c4d5e6f7'
down_revision: Union[str, None] = 'j1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'analysis_jobs',
        sa.Column(
            'connection_id',
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey('whatsapp_connections.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.create_index('ix_analysis_jobs_connection_id', 'analysis_jobs', ['connection_id'])


def downgrade() -> None:
    op.drop_index('ix_analysis_jobs_connection_id', 'analysis_jobs')
    op.drop_column('analysis_jobs', 'connection_id')
