"""Add auction_url to auctions and current_location to vehicles

Revision ID: 3c4d5e6f0a1b
Revises: 9a2b7c1d
Create Date: 2025-10-13 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3c4d5e6f0a1b'
down_revision = '9a2b7c1d'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('auctions') as batch_op:
        batch_op.add_column(sa.Column('auction_url', sa.Text(), nullable=True))
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('current_location', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.drop_column('current_location')
    with op.batch_alter_table('auctions') as batch_op:
        batch_op.drop_column('auction_url')
