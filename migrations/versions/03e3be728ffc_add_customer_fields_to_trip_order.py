"""add_customer_fields_to_trip_order

Revision ID: 03e3be728ffc
Revises: fbc389ed73ff
Create Date: 2025-09-04 10:08:41.391357

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03e3be728ffc'
down_revision = 'fbc389ed73ff'
branch_labels = None
depends_on = None


def upgrade():
    # Add customer fields to trip_order table
    op.add_column('trip_order', sa.Column('customer_name', sa.String(200), nullable=True))
    op.add_column('trip_order', sa.Column('customer_location', sa.String(200), nullable=True))


def downgrade():
    # Remove customer fields from trip_order table
    op.drop_column('trip_order', 'customer_location')
    op.drop_column('trip_order', 'customer_name')
