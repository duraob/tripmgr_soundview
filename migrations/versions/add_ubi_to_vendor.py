"""Add UBI field to Vendor model

Revision ID: add_ubi_to_vendor
Revises: c159292fbe69
Create Date: 2025-01-19 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_ubi_to_vendor'
down_revision = '5387a890448f'
branch_labels = None
depends_on = None


def upgrade():
    # Add UBI column to vendor table
    op.add_column('vendor', sa.Column('ubi', sa.String(100), nullable=True))


def downgrade():
    # Remove UBI column from vendor table
    op.drop_column('vendor', 'ubi')
