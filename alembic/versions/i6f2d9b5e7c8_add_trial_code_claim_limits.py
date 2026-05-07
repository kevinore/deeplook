"""add_trial_code_claim_limits

Revision ID: i6f2d9b5e7c8
Revises: h5e1c8a4d6b9
Create Date: 2026-05-07 12:00:00.000000

Replaces the single-use redemption model (redeemed_by_client_id / redeemed_at)
with a counter-based model (max_claims / claims_count), allowing a code to be
claimed by up to max_claims different users. The per-client "one trial per
lifetime" invariant is still enforced via clients.trial_redeemed_at.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'i6f2d9b5e7c8'
down_revision: Union[str, None] = 'h5e1c8a4d6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_trial_codes_redeemed_by', table_name='trial_codes')
    op.drop_constraint('trial_codes_redeemed_by_client_id_fkey', 'trial_codes', type_='foreignkey')
    op.drop_column('trial_codes', 'redeemed_by_client_id')
    op.drop_column('trial_codes', 'redeemed_at')

    op.add_column('trial_codes', sa.Column('max_claims', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('trial_codes', sa.Column('claims_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('trial_codes', 'claims_count')
    op.drop_column('trial_codes', 'max_claims')

    op.add_column('trial_codes', sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trial_codes', sa.Column('redeemed_by_client_id', sa.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        'trial_codes_redeemed_by_client_id_fkey',
        'trial_codes', 'clients',
        ['redeemed_by_client_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_trial_codes_redeemed_by', 'trial_codes', ['redeemed_by_client_id'])
