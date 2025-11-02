"""Ensure buyers link to customers

Revision ID: add_customer_fk_to_buyers_20251102_01
Revises: link_payment_vehicle_customer_20251028_04
Create Date: 2025-11-02 00:00:00.000000

"""
from typing import Any

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_customer_fk_to_buyers_20251102_01"
down_revision = "link_payment_vehicle_customer_20251028_04"
branch_labels = None
depends_on = None


def _table_has_column(inspector: Any, table: str, column: str) -> bool:
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def _table_foreign_keys(inspector: Any, table: str) -> set[str]:
    try:
        return {fk.get("name") for fk in inspector.get_foreign_keys(table) if fk.get("name")}
    except Exception:
        return set()


def _table_indexes(inspector: Any, table: str) -> set[str]:
    try:
        return {idx.get("name") for idx in inspector.get_indexes(table) if idx.get("name")}
    except Exception:
        return set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    has_customer_id = _table_has_column(inspector, "buyers", "customer_id")
    existing_fks = _table_foreign_keys(inspector, "buyers")
    existing_indexes = _table_indexes(inspector, "buyers")

    with op.batch_alter_table("buyers") as batch_op:
        if not has_customer_id:
            batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))

        if "fk_buyers_customer_id_customers" not in existing_fks:
            batch_op.create_foreign_key(
                "fk_buyers_customer_id_customers",
                "customers",
                ["customer_id"],
                ["id"],
                ondelete="SET NULL",
            )

        if "ix_buyers_customer_id" not in existing_indexes:
            batch_op.create_index("ix_buyers_customer_id", ["customer_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_fks = _table_foreign_keys(inspector, "buyers")
    existing_indexes = _table_indexes(inspector, "buyers")
    has_customer_id = _table_has_column(inspector, "buyers", "customer_id")

    with op.batch_alter_table("buyers") as batch_op:
        if "fk_buyers_customer_id_customers" in existing_fks:
            try:
                batch_op.drop_constraint("fk_buyers_customer_id_customers", type_="foreignkey")
            except Exception:
                pass

        if "ix_buyers_customer_id" in existing_indexes:
            try:
                batch_op.drop_index("ix_buyers_customer_id")
            except Exception:
                pass

        if has_customer_id:
            try:
                batch_op.drop_column("customer_id")
            except Exception:
                pass
