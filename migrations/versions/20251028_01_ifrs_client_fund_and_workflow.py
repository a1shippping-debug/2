"""IFRS: add client fund flag, workflow, settings fields

Revision ID: ifrs_client_fund_20251028_01
Revises: add_price_category_20251027_02
Create Date: 2025-10-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ifrs_client_fund_20251028_01'
down_revision = 'add_price_category_20251027_02'
branch_labels = None
depends_on = None


def upgrade():
    # Journal entries: client fund flag + workflow columns
    with op.batch_alter_table('journal_entries') as batch_op:
        batch_op.add_column(sa.Column('is_client_fund', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='approved'))
        batch_op.add_column(sa.Column('notes', sa.Text()))
        batch_op.add_column(sa.Column('approved_by_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key('fk_journal_entries_approved_by_user_id_users', 'users', ['approved_by_user_id'], ['id'])
        # Remove server defaults after backfill
        batch_op.alter_column('is_client_fund', server_default=None)
        batch_op.alter_column('status', server_default=None)

    # Settings: lock date and accounting method
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('books_locked_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('accounting_method', sa.String(length=10), nullable=True, server_default='accrual'))
        batch_op.alter_column('accounting_method', server_default=None)


def downgrade():
    with op.batch_alter_table('journal_entries') as batch_op:
        try:
            batch_op.drop_constraint('fk_journal_entries_approved_by_user_id_users', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by_user_id')
        batch_op.drop_column('notes')
        batch_op.drop_column('status')
        batch_op.drop_column('is_client_fund')

    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('accounting_method')
        batch_op.drop_column('books_locked_until')
