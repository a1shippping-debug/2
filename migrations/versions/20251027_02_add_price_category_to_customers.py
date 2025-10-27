"""add price_category to customers

Revision ID: add_price_category_20251027_02
Revises: add_category_20251027_01
Create Date: 2025-10-27 00:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_price_category_20251027_02'
down_revision = 'add_category_20251027_01'
branch_labels = None
depends_on = None

def upgrade():
    # Add price_category to customers with default 'normal', then drop default
    with op.batch_alter_table('customers') as batch_op:
        batch_op.add_column(sa.Column('price_category', sa.String(length=20), nullable=False, server_default='normal'))
    with op.batch_alter_table('customers') as batch_op:
        batch_op.alter_column('price_category', server_default=None)


def downgrade():
    with op.batch_alter_table('customers') as batch_op:
        batch_op.drop_column('price_category')
