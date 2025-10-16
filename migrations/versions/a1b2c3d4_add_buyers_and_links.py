"""Add buyers table and link auctions to buyer and customer

Revision ID: a1b2c3d4
Revises: 9a2b7c1d
Create Date: 2025-10-16 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4'
down_revision = '9a2b7c1d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'buyers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
    )
    with op.batch_alter_table('auctions') as batch_op:
        batch_op.add_column(sa.Column('buyer_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_auctions_buyer', 'buyers', ['buyer_id'], ['id'])
        batch_op.create_foreign_key('fk_auctions_customer', 'customers', ['customer_id'], ['id'])


def downgrade():
    with op.batch_alter_table('auctions') as batch_op:
        try:
            batch_op.drop_constraint('fk_auctions_buyer', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('fk_auctions_customer', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('buyer_id')
        batch_op.drop_column('customer_id')
    op.drop_table('buyers')
