"""add vehicle sale listings

Revision ID: fea1e2d3c4b5
Revises: cd6f9d90c5b1
Create Date: 2025-10-16 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fea1e2d3c4b5'
down_revision = 'cd6f9d90c5b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vehicle_sale_listings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer(), nullable=False, index=True),
        sa.Column('asking_price_omr', sa.Numeric(12, 3), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Pending'),
        sa.Column('note_admin', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decided_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id']),
    )
    op.create_index('ix_vehicle_sale_listings_vehicle_id', 'vehicle_sale_listings', ['vehicle_id'])
    op.create_index('ix_vehicle_sale_listings_customer_id', 'vehicle_sale_listings', ['customer_id'])


def downgrade():
    op.drop_index('ix_vehicle_sale_listings_customer_id', table_name='vehicle_sale_listings')
    op.drop_index('ix_vehicle_sale_listings_vehicle_id', table_name='vehicle_sale_listings')
    op.drop_table('vehicle_sale_listings')
