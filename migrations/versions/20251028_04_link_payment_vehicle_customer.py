"""Link payments to vehicle and customer

Revision ID: link_payment_vehicle_customer_20251028_04
Revises: vehicle_subledgers_20251028_03
Create Date: 2025-10-28 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'link_payment_vehicle_customer_20251028_04'
down_revision = 'vehicle_subledgers_20251028_03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payments') as batch_op:
        batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('vehicle_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_payments_customer_id_customers', 'customers', ['customer_id'], ['id'])
        batch_op.create_foreign_key('fk_payments_vehicle_id_vehicles', 'vehicles', ['vehicle_id'], ['id'])
        batch_op.create_index('ix_payments_customer_id', ['customer_id'], unique=False)
        batch_op.create_index('ix_payments_vehicle_id', ['vehicle_id'], unique=False)


def downgrade():
    with op.batch_alter_table('payments') as batch_op:
        try:
            batch_op.drop_constraint('fk_payments_vehicle_id_vehicles', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('fk_payments_customer_id_customers', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_index('ix_payments_vehicle_id')
        except Exception:
            pass
        try:
            batch_op.drop_index('ix_payments_customer_id')
        except Exception:
            pass
        try:
            batch_op.drop_column('vehicle_id')
        except Exception:
            pass
        try:
            batch_op.drop_column('customer_id')
        except Exception:
            pass
