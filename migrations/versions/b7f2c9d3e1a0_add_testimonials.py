"""add testimonials table

Revision ID: b7f2c9d3e1a0
Revises: a2cd544a6768
Create Date: 2025-10-16 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f2c9d3e1a0'
down_revision = 'a2cd544a6768'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'testimonials',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('role', sa.String(length=150), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('approved', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_testimonials_created_at', 'testimonials', ['created_at'], unique=False)


def downgrade():
    op.drop_index('ix_testimonials_created_at', table_name='testimonials')
    op.drop_table('testimonials')
