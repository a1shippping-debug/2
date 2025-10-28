"""Client sub-ledgers: per-client accounts and structure table

Revision ID: client_subledgers_20251028_02
Revises: ifrs_client_fund_20251028_01
Create Date: 2025-10-28 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'client_subledgers_20251028_02'
down_revision = 'ifrs_client_fund_20251028_01'
branch_labels = None
depends_on = None


def upgrade():
    # accounts: optional client link
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_accounts_client_id_customers', 'customers', ['client_id'], ['id'])
        batch_op.create_index('ix_accounts_client_id', ['client_id'], unique=False)

    # client account structure table
    op.create_table(
        'client_account_structures',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.Integer(), nullable=False, index=True, unique=True),
        sa.Column('deposit_account_code', sa.String(length=20), nullable=False),
        sa.Column('auction_account_code', sa.String(length=20), nullable=True),
        sa.Column('service_revenue_account_code', sa.String(length=20), nullable=False),
        sa.Column('logistics_expense_account_code', sa.String(length=20), nullable=False),
        sa.Column('receivable_account_code', sa.String(length=20), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='OMR'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name='fk_client_accounts_customer_id_customers'),
        sa.UniqueConstraint('customer_id', name='uq_client_account_structures_customer_id'),
    )


def downgrade():
    # drop client structure
    op.drop_table('client_account_structures')

    # drop accounts link
    with op.batch_alter_table('accounts') as batch_op:
        try:
            batch_op.drop_constraint('fk_accounts_client_id_customers', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_index('ix_accounts_client_id')
        except Exception:
            pass
        batch_op.drop_column('client_id')
