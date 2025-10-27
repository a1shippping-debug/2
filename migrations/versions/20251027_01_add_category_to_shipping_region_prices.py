"""add category to shipping_region_prices

Revision ID: add_category_20251027_01
Revises: 44c2b80c7bec
Create Date: 2025-10-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_category_20251027_01'
down_revision = '44c2b80c7bec'
branch_labels = None
depends_on = None

def upgrade():
    # Add category column with default 'normal'
    with op.batch_alter_table('shipping_region_prices') as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=20), nullable=False, server_default='normal'))
    # Remove server default after backfilling existing rows
    with op.batch_alter_table('shipping_region_prices') as batch_op:
        batch_op.alter_column('category', server_default=None)
    # Drop old unique index on region_code if exists and create composite unique
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    # Drop index ix_shipping_region_prices_region_code if present
    try:
        batch = op.batch_alter_table('shipping_region_prices')
        batch.drop_index('ix_shipping_region_prices_region_code')
        batch.commit()
    except Exception:
        try:
            op.drop_index('ix_shipping_region_prices_region_code', table_name='shipping_region_prices')
        except Exception:
            pass
    # Create new composite unique constraint
    with op.batch_alter_table('shipping_region_prices') as batch_op:
        batch_op.create_unique_constraint('uq_shipping_region_code_category', ['region_code', 'category'])


def downgrade():
    # Drop composite constraint
    with op.batch_alter_table('shipping_region_prices') as batch_op:
        try:
            batch_op.drop_constraint('uq_shipping_region_code_category', type_='unique')
        except Exception:
            pass
    # Recreate unique index on region_code
    try:
        op.create_index('ix_shipping_region_prices_region_code', 'shipping_region_prices', ['region_code'], unique=True)
    except Exception:
        pass
    # Drop category column
    with op.batch_alter_table('shipping_region_prices') as batch_op:
        batch_op.drop_column('category')
