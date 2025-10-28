"""Vehicle sub-ledgers: per-vehicle accounts and structure table

Revision ID: vehicle_subledgers_20251028_03
Revises: client_subledgers_20251028_02
Create Date: 2025-10-28 01:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'vehicle_subledgers_20251028_03'
down_revision = 'client_subledgers_20251028_02'
branch_labels = None
depends_on = None


def upgrade():
    # accounts: optional vehicle link
    with op.batch_alter_table('accounts') as batch_op:
        batch_op.add_column(sa.Column('vehicle_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_accounts_vehicle_id_vehicles', 'vehicles', ['vehicle_id'], ['id'])
        batch_op.create_index('ix_accounts_vehicle_id', ['vehicle_id'], unique=False)

    # vehicle account structure table
    op.create_table(
        'vehicle_account_structures',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('deposit_account_code', sa.String(length=20), nullable=False),
        sa.Column('auction_account_code', sa.String(length=20), nullable=False),
        sa.Column('freight_account_code', sa.String(length=20), nullable=False),
        sa.Column('customs_account_code', sa.String(length=20), nullable=False),
        sa.Column('commission_account_code', sa.String(length=20), nullable=False),
        sa.Column('storage_account_code', sa.String(length=20), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='OMR'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name='fk_vehicle_accounts_vehicle_id_vehicles'),
        sa.ForeignKeyConstraint(['client_id'], ['customers.id'], name='fk_vehicle_accounts_client_id_customers'),
        sa.UniqueConstraint('vehicle_id', name='uq_vehicle_account_structures_vehicle_id'),
    )
    op.create_index('ix_vehicle_account_structures_vehicle_id', 'vehicle_account_structures', ['vehicle_id'], unique=True)
    op.create_index('ix_vehicle_account_structures_client_id', 'vehicle_account_structures', ['client_id'], unique=False)


def downgrade():
    # drop vehicle structure
    try:
        op.drop_index('ix_vehicle_account_structures_client_id', table_name='vehicle_account_structures')
    except Exception:
        pass
    try:
        op.drop_index('ix_vehicle_account_structures_vehicle_id', table_name='vehicle_account_structures')
    except Exception:
        pass
    op.drop_table('vehicle_account_structures')

    # drop accounts link
    with op.batch_alter_table('accounts') as batch_op:
        try:
            batch_op.drop_constraint('fk_accounts_vehicle_id_vehicles', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.drop_index('ix_accounts_vehicle_id')
        except Exception:
            pass
        try:
            batch_op.drop_column('vehicle_id')
        except Exception:
            pass
