"""Drop customer_contact table

Revision ID: drop_customer_contact
Revises: remove_email_doc
Create Date: 2025-02-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'drop_customer_contact'
down_revision = 'remove_email_doc'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('customer_contact')


def downgrade():
    op.create_table(
        'customer_contact',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('contact_name', sa.String(200), nullable=False),
        sa.Column('email', sa.String(200), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendor.id']),
        sa.PrimaryKeyConstraint('id'),
    )
