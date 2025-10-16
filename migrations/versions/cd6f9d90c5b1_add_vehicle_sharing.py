"""add vehicle sharing fields

Revision ID: cd6f9d90c5b1
Revises: ebca1bfc31e8
Create Date: 2025-10-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cd6f9d90c5b1'
down_revision = 'ebca1bfc31e8'
branch_labels = None
depends_on = None


def upgrade():
    # Add sharing fields to vehicles
    op.add_column('vehicles', sa.Column('share_token', sa.String(length=64), nullable=True))
    op.add_column('vehicles', sa.Column('share_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    # Unique index for token-based lookup
    op.create_index('ix_vehicles_share_token', 'vehicles', ['share_token'], unique=True)


def downgrade():
    # Drop index and columns
    op.drop_index('ix_vehicles_share_token', table_name='vehicles')
    op.drop_column('vehicles', 'share_enabled')
    op.drop_column('vehicles', 'share_token')
