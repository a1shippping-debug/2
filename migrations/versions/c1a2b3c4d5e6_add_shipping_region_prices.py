"""add shipping region prices table

Revision ID: c1a2b3c4d5e6
Revises: b7f2c9d3e1a0
Create Date: 2025-10-16 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a2b3c4d5e6'
down_revision = 'b7f2c9d3e1a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_region_prices',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('region_code', sa.String(length=50), nullable=False),
        sa.Column('region_name', sa.String(length=200), nullable=True),
        sa.Column('price_omr', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('effective_from', sa.DateTime(), nullable=True),
        sa.Column('effective_to', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint('uq_shipping_region_prices_region_code', 'shipping_region_prices', ['region_code'])
    op.create_index('ix_shipping_region_prices_region_code', 'shipping_region_prices', ['region_code'], unique=False)


def downgrade():
    op.drop_index('ix_shipping_region_prices_region_code', table_name='shipping_region_prices')
    op.drop_constraint('uq_shipping_region_prices_region_code', 'shipping_region_prices', type_='unique')
    op.drop_table('shipping_region_prices')
