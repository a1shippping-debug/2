"""Operations portal: customers/vehicles/shipments extensions, docs, notifications

Revision ID: 9a2b7c1d
Revises: 7b1e8d8b3d9a
Create Date: 2025-10-13 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a2b7c1d'
down_revision = '7b1e8d8b3d9a'
branch_labels = None
depends_on = None


def upgrade():
    # customers new columns
    with op.batch_alter_table('customers') as batch_op:
        batch_op.add_column(sa.Column('full_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('country', sa.String(length=100), nullable=True))

    # vehicles
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('purchase_date', sa.DateTime(), nullable=True))

    # shipments
    with op.batch_alter_table('shipments') as batch_op:
        batch_op.add_column(sa.Column('cost_insurance_usd', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('shipping_company', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('container_number', sa.String(length=100), nullable=True))

    # documents
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('shipment_id', sa.Integer(), nullable=True),
        sa.Column('doc_type', sa.String(length=100), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id']),
    )
    op.create_index('ix_documents_vehicle_id', 'documents', ['vehicle_id'])
    op.create_index('ix_documents_shipment_id', 'documents', ['shipment_id'])

    # notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message', sa.String(length=255), nullable=True),
        sa.Column('level', sa.String(length=20), nullable=True),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )


def downgrade():
    op.drop_table('notifications')
    op.drop_index('ix_documents_shipment_id', table_name='documents')
    op.drop_index('ix_documents_vehicle_id', table_name='documents')
    op.drop_table('documents')

    with op.batch_alter_table('shipments') as batch_op:
        batch_op.drop_column('container_number')
        batch_op.drop_column('shipping_company')
        batch_op.drop_column('cost_insurance_usd')

    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.drop_column('purchase_date')

    with op.batch_alter_table('customers') as batch_op:
        batch_op.drop_column('country')
        batch_op.drop_column('phone')
        batch_op.drop_column('email')
        batch_op.drop_column('full_name')

    # no buyer/customer changes in this revision
