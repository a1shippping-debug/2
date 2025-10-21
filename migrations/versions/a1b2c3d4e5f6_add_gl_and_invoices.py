"""Add GL tables, exchange rates, deposits, and invoice fields

Revision ID: a1b2c3d4e5f6
Revises: 6b04a955f9cf
Create Date: 2025-10-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6b04a955f9cf'
branch_labels = None
depends_on = None


def upgrade():
    # Accounts (Chart of Accounts)
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='OMR'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('code')
    )
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_accounts_code'), ['code'], unique=True)

    # Exchange rates
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('base_currency', sa.String(length=3), nullable=False),
        sa.Column('quote_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('effective_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # Journal entries and lines
    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entry_date', sa.DateTime(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('auction_id', sa.Integer(), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['auction_id'], ['auctions.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
    )
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_journal_entries_entry_date'), ['entry_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entries_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entries_vehicle_id'), ['vehicle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entries_auction_id'), ['auction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_entries_invoice_id'), ['invoice_id'], unique=False)

    op.create_table(
        'journal_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('debit', sa.Numeric(precision=14, scale=3), nullable=True, server_default='0'),
        sa.Column('credit', sa.Numeric(precision=14, scale=3), nullable=True, server_default='0'),
        sa.Column('currency_code', sa.String(length=3), nullable=True, server_default='OMR'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id']),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
    )
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_journal_lines_entry_id'), ['entry_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_lines_account_id'), ['account_id'], unique=False)

    # Operational expenses
    op.create_table(
        'operational_expenses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('auction_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('original_amount', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('original_currency', sa.String(length=3), nullable=True, server_default='OMR'),
        sa.Column('amount_omr', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('exchange_rate_id', sa.Integer(), nullable=True),
        sa.Column('paid', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('supplier', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['auction_id'], ['auctions.id']),
        sa.ForeignKeyConstraint(['exchange_rate_id'], ['exchange_rates.id']),
    )
    with op.batch_alter_table('operational_expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_operational_expenses_vehicle_id'), ['vehicle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_operational_expenses_auction_id'), ['auction_id'], unique=False)

    # Customer deposits
    op.create_table(
        'customer_deposits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('auction_id', sa.Integer(), nullable=True),
        sa.Column('amount_omr', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('method', sa.String(length=50), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='held'),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('refunded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['auction_id'], ['auctions.id']),
    )
    with op.batch_alter_table('customer_deposits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customer_deposits_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_deposits_vehicle_id'), ['vehicle_id'], unique=False)

    # Alter invoices: add invoice_type, vehicle_id, exchange_rate_id
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invoice_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('vehicle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('exchange_rate_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_invoices_vehicle_id'), ['vehicle_id'], unique=False)
        batch_op.create_foreign_key(None, 'vehicles', ['vehicle_id'], ['id'])
        batch_op.create_foreign_key(None, 'exchange_rates', ['exchange_rate_id'], ['id'])

    # Seed a minimal chart of accounts
    accounts = sa.table(
        'accounts',
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('type', sa.String),
        sa.column('currency_code', sa.String),
        sa.column('active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
    )
    op.bulk_insert(
        accounts,
        [
            {'code': 'A100', 'name': 'Bank', 'type': 'ASSET', 'currency_code': 'OMR', 'active': True},
            {'code': 'A110', 'name': 'Cash', 'type': 'ASSET', 'currency_code': 'OMR', 'active': True},
            {'code': 'A200', 'name': 'Inventory - Vehicles', 'type': 'ASSET', 'currency_code': 'OMR', 'active': True},
            {'code': 'L200', 'name': 'Customer Deposits', 'type': 'LIABILITY', 'currency_code': 'OMR', 'active': True},
            {'code': 'L210', 'name': 'Accounts Payable - Supplier', 'type': 'LIABILITY', 'currency_code': 'OMR', 'active': True},
            {'code': 'R100', 'name': 'Car Sales Revenue', 'type': 'REVENUE', 'currency_code': 'OMR', 'active': True},
            {'code': 'R150', 'name': 'Additional Revenue', 'type': 'REVENUE', 'currency_code': 'OMR', 'active': True},
            {'code': 'R300', 'name': 'Fines Revenue', 'type': 'REVENUE', 'currency_code': 'OMR', 'active': True},
            {'code': 'E200', 'name': 'Operational Expenses', 'type': 'EXPENSE', 'currency_code': 'OMR', 'active': True},
            {'code': 'E210', 'name': 'Internal Shipping Expenses', 'type': 'EXPENSE', 'currency_code': 'OMR', 'active': True},
        ]
    )


def downgrade():
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_invoices_vehicle_id'))
        batch_op.drop_column('exchange_rate_id')
        batch_op.drop_column('vehicle_id')
        batch_op.drop_column('invoice_type')

    with op.batch_alter_table('customer_deposits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customer_deposits_vehicle_id'))
        batch_op.drop_index(batch_op.f('ix_customer_deposits_customer_id'))
    op.drop_table('customer_deposits')

    with op.batch_alter_table('operational_expenses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_operational_expenses_auction_id'))
        batch_op.drop_index(batch_op.f('ix_operational_expenses_vehicle_id'))
    op.drop_table('operational_expenses')

    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_journal_lines_account_id'))
        batch_op.drop_index(batch_op.f('ix_journal_lines_entry_id'))
    op.drop_table('journal_lines')

    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_journal_entries_invoice_id'))
        batch_op.drop_index(batch_op.f('ix_journal_entries_auction_id'))
        batch_op.drop_index(batch_op.f('ix_journal_entries_vehicle_id'))
        batch_op.drop_index(batch_op.f('ix_journal_entries_customer_id'))
        batch_op.drop_index(batch_op.f('ix_journal_entries_entry_date'))
    op.drop_table('journal_entries')

    op.drop_table('exchange_rates')

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accounts_code'))
    op.drop_table('accounts')
