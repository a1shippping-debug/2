"""Add accounting portal tables and settings column

Revision ID: 7b1e8d8b3d9a
Revises: e55898043780
Create Date: 2025-10-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7b1e8d8b3d9a'
down_revision = 'e55898043780'
branch_labels = None
depends_on = None

def upgrade():
    # invoice items
    op.create_table(
        'invoice_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('amount_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
    )
    op.create_index('ix_invoice_items_invoice_id', 'invoice_items', ['invoice_id'])

    # payments
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('amount_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('method', sa.String(length=50), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
    )
    op.create_index('ix_payments_invoice_id', 'payments', ['invoice_id'])

    # international costs
    op.create_table(
        'international_costs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('freight_usd', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('insurance_usd', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('auction_fees_usd', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('customs_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('vat_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('local_transport_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('misc_omr', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.UniqueConstraint('vehicle_id'),
    )

    # bills of lading
    op.create_table(
        'bills_of_lading',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bol_number', sa.String(length=100), nullable=True),
        sa.Column('shipment_id', sa.Integer(), nullable=True),
        sa.Column('issue_date', sa.DateTime(), nullable=True),
        sa.Column('pdf_path', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
        sa.UniqueConstraint('bol_number'),
    )

    # settings extension
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('insurance_rate', sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade():
    # revert settings extension
    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('insurance_rate')

    op.drop_index('ix_payments_invoice_id', table_name='payments')
    op.drop_table('payments')

    op.drop_index('ix_invoice_items_invoice_id', table_name='invoice_items')
    op.drop_table('invoice_items')

    op.drop_table('bills_of_lading')
    op.drop_table('international_costs')
