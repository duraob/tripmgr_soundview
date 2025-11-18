"""add_performance_indexes

Revision ID: a1b2c3d4e5f6
Revises: 03e3be728ffc
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '03e3be728ffc'
branch_labels = None
depends_on = None


def upgrade():
    # Add indexes for frequently queried columns
    op.create_index('idx_trip_order_trip_id', 'trip_order', ['trip_id'], unique=False)
    op.create_index('idx_trip_order_vendor_id', 'trip_order', ['vendor_id'], unique=False)
    op.create_index('idx_trip_order_order_id', 'trip_order', ['order_id'], unique=False)
    op.create_index('idx_trip_order_status', 'trip_order', ['status'], unique=False)
    op.create_index('idx_location_mapping_dispensary_id', 'location_mapping', ['leaftrade_dispensary_location_id'], unique=False)
    op.create_index('idx_location_mapping_vendor_id', 'location_mapping', ['biotrack_vendor_id'], unique=False)
    op.create_index('idx_trip_date_created', 'trip', ['date_created'], unique=False)
    op.create_index('idx_trip_execution_status', 'trip', ['execution_status'], unique=False)


def downgrade():
    # Remove indexes
    op.drop_index('idx_trip_execution_status', table_name='trip')
    op.drop_index('idx_trip_date_created', table_name='trip')
    op.drop_index('idx_location_mapping_vendor_id', table_name='location_mapping')
    op.drop_index('idx_location_mapping_dispensary_id', table_name='location_mapping')
    op.drop_index('idx_trip_order_status', table_name='trip_order')
    op.drop_index('idx_trip_order_order_id', table_name='trip_order')
    op.drop_index('idx_trip_order_vendor_id', table_name='trip_order')
    op.drop_index('idx_trip_order_trip_id', table_name='trip_order')

