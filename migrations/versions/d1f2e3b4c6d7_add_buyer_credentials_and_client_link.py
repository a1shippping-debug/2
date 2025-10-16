"""add buyer credentials and client link

Revision ID: d1f2e3b4c6d7
Revises: cd6f9d90c5b1
Create Date: 2025-10-16 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f2e3b4c6d7'
down_revision = 'cd6f9d90c5b1'
branch_labels = None
depends_on = None


def upgrade():
    # Add optional buyer credentials and client link
    op.add_column('buyers', sa.Column('buyer_number', sa.String(length=100), nullable=True))
    op.add_column('buyers', sa.Column('password', sa.String(length=200), nullable=True))
    op.add_column('buyers', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.create_index('ix_buyers_buyer_number', 'buyers', ['buyer_number'], unique=False)
    op.create_foreign_key('fk_buyers_customer_id_customers', 'buyers', 'customers', ['customer_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_buyers_customer_id_customers', 'buyers', type_='foreignkey')
    op.drop_index('ix_buyers_buyer_number', table_name='buyers')
    op.drop_column('buyers', 'customer_id')
    op.drop_column('buyers', 'password')
    op.drop_column('buyers', 'buyer_number')
