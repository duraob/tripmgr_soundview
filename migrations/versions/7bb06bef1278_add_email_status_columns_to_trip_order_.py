"""add_email_status_columns_to_trip_order_table

Revision ID: 7bb06bef1278
Revises: 410230443e74
Create Date: 2025-09-01 11:51:38.512146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7bb06bef1278'
down_revision = '410230443e74'
branch_labels = None
depends_on = None


def upgrade():
    # Add email status columns to trip_order table
    op.add_column('trip_order', sa.Column('manifest_attached', sa.Boolean(), nullable=True))
    op.add_column('trip_order', sa.Column('invoice_attached', sa.Boolean(), nullable=True))
    op.add_column('trip_order', sa.Column('email_ready', sa.Boolean(), nullable=True))


def downgrade():
    # Remove email status columns from trip_order table
    op.drop_column('trip_order', 'email_ready')
    op.drop_column('trip_order', 'invoice_attached')
    op.drop_column('trip_order', 'manifest_attached')
