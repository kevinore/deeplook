"""add_trial_codes_table_and_client_redemption_marker

Revision ID: h5e1c8a4d6b9
Revises: g4d9c1e2f3b5
Create Date: 2026-05-05 12:00:00.000000

Introduces single-use trial codes that grant a client temporary access to the
`basic` plan without going through Wompi. Each client may redeem at most once
(enforced via `clients.trial_redeemed_at` being non-null), and each code may
be claimed by at most one client (enforced via the row-level redeem update).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'h5e1c8a4d6b9'
down_revision: Union[str, None] = 'g4d9c1e2f3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'clients',
        sa.Column('trial_redeemed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'trial_codes',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('code', sa.String(64), nullable=False, unique=True),
        sa.Column('plan', sa.String(50), nullable=False, server_default='basic'),
        sa.Column('duration_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('redeemed_by_client_id', postgresql.UUID(as_uuid=False),
                  sa.ForeignKey('clients.id', ondelete='SET NULL'), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('note', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_trial_codes_code', 'trial_codes', ['code'], unique=True)
    op.create_index('ix_trial_codes_redeemed_by', 'trial_codes', ['redeemed_by_client_id'])


def downgrade() -> None:
    op.drop_index('ix_trial_codes_redeemed_by', table_name='trial_codes')
    op.drop_index('ix_trial_codes_code', table_name='trial_codes')
    op.drop_table('trial_codes')
    op.drop_column('clients', 'trial_redeemed_at')
