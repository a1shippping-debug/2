"""Add container and booking numbers to vehicles

Revision ID: vehicle_shipping_fields_20251102_01
Revises: link_payment_vehicle_customer_20251028_04
Create Date: 2025-11-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "vehicle_shipping_fields_20251102_01"
down_revision = "link_payment_vehicle_customer_20251028_04"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.add_column(sa.Column("container_number", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("booking_number", sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table("vehicles") as batch_op:
        try:
            batch_op.drop_column("booking_number")
        except Exception:
            pass
        try:
            batch_op.drop_column("container_number")
        except Exception:
            pass
