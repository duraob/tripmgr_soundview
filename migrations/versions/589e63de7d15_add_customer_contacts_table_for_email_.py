"""add_customer_contacts_table_for_email_delivery

Revision ID: 589e63de7d15
Revises: add_ubi_to_vendor
Create Date: 2025-09-01 11:51:06.361434

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '589e63de7d15'
down_revision = 'add_ubi_to_vendor'
branch_labels = None
depends_on = None


def upgrade():
    # Create customer_contacts table
    op.create_table('customer_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('contact_name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendor.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_customer_contacts_vendor', 'customer_contacts', ['vendor_id'], unique=False)


def downgrade():
    # Drop customer_contacts table
    op.drop_index('idx_customer_contacts_vendor', table_name='customer_contacts')
    op.drop_table('customer_contacts')
