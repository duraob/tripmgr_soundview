"""add_vendor_relationship_to_trip_order

Revision ID: e89537f39501
Revises: 03e3be728ffc
Create Date: 2025-09-04 10:27:22.219304

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e89537f39501'
down_revision = '03e3be728ffc'
branch_labels = None
depends_on = None


def upgrade():
    # Add vendor relationship to trip_order table
    op.add_column('trip_order', sa.Column('vendor_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_trip_order_vendor', 'trip_order', 'vendor', ['vendor_id'], ['id'])


def downgrade():
    # Remove vendor relationship from trip_order table
    op.drop_constraint('fk_trip_order_vendor', 'trip_order', type_='foreignkey')
    op.drop_column('trip_order', 'vendor_id')
