"""add_policies_accepted_at_to_clients

Revision ID: g4d9c1e2f3b5
Revises: f3a8b2c5d9e1
Create Date: 2026-04-29 19:30:00.000000

Adds explicit consent tracking on `clients`. Required by Colombia's Ley 1581
de 2012 (Habeas Data) and Decreto 1377 de 2013 — the responsable del
tratamiento must record WHEN the titular gave consent.

Stored as a timestamp (not just a boolean) so we can prove consent at a
specific point in time if asked by the SIC. Captured on onboarding modal
submission.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'g4d9c1e2f3b5'
down_revision: Union[str, None] = 'f3a8b2c5d9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'clients',
        sa.Column('policies_accepted_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: existing clients are presumed to have accepted at account creation
    # (they couldn't have used the platform otherwise). Set to created_at.
    op.execute(
        "UPDATE clients SET policies_accepted_at = created_at "
        "WHERE policies_accepted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column('clients', 'policies_accepted_at')
