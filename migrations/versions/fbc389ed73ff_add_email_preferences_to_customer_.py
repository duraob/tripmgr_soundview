"""add_email_preferences_to_customer_contacts

Revision ID: fbc389ed73ff
Revises: 7bb06bef1278
Create Date: 2025-09-01 12:11:24.014485

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fbc389ed73ff'
down_revision = '7bb06bef1278'
branch_labels = None
depends_on = None


def upgrade():
    # Add email preference columns to customer_contacts table
    op.add_column('customer_contacts', sa.Column('email_invoice', sa.Boolean(), nullable=True))
    op.add_column('customer_contacts', sa.Column('email_manifest', sa.Boolean(), nullable=True))


def downgrade():
    # Remove email preference columns from customer_contacts table
    op.drop_column('customer_contacts', 'email_manifest')
    op.drop_column('customer_contacts', 'email_invoice')
