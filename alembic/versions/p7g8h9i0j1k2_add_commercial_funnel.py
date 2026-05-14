"""add commercial funnel fields to conversation_analysis

Revision ID: p7g8h9i0j1k2
Revises: o6f7g8h9i0j1
Create Date: 2026-05-12

"""
from alembic import op
import sqlalchemy as sa

revision = 'p7g8h9i0j1k2'
down_revision = 'o6f7g8h9i0j1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversation_analysis',
        sa.Column('has_purchase_intent', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('conversation_analysis',
        sa.Column('intent_stage', sa.String(30), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('intent_first_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('quote_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('quote_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('quote_response_time_seconds', sa.Integer(), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('post_quote_followup_count', sa.Integer(), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('followup_delay_hours', sa.Float(), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('lost_reason', sa.String(30), nullable=True))
    op.add_column('conversation_analysis',
        sa.Column('lost_reason_detail', sa.Text(), nullable=True))
    # Partial index for the most common funnel query
    op.create_index(
        'ix_ca_purchase_intent',
        'conversation_analysis',
        ['has_purchase_intent', 'analysis_job_id'],
        postgresql_where=sa.text('has_purchase_intent = true'),
    )


def downgrade() -> None:
    op.drop_index('ix_ca_purchase_intent', table_name='conversation_analysis')
    op.drop_column('conversation_analysis', 'lost_reason_detail')
    op.drop_column('conversation_analysis', 'lost_reason')
    op.drop_column('conversation_analysis', 'followup_delay_hours')
    op.drop_column('conversation_analysis', 'post_quote_followup_count')
    op.drop_column('conversation_analysis', 'quote_response_time_seconds')
    op.drop_column('conversation_analysis', 'quote_sent_at')
    op.drop_column('conversation_analysis', 'quote_requested_at')
    op.drop_column('conversation_analysis', 'intent_first_at')
    op.drop_column('conversation_analysis', 'intent_stage')
    op.drop_column('conversation_analysis', 'has_purchase_intent')
