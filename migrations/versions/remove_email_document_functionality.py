"""remove_email_document_functionality

Revision ID: remove_email_doc
Revises: 454acb38516c
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'remove_email_doc'
down_revision = '454acb38516c'
branch_labels = None
depends_on = None


def upgrade():
    # Drop email/document columns from trip_order
    op.drop_column('trip_order', 'email_ready')
    op.drop_column('trip_order', 'manifest_attached')
    op.drop_column('trip_order', 'invoice_attached')
    
    # Drop email preference columns from customer_contact
    op.drop_column('customer_contact', 'email_invoice')
    op.drop_column('customer_contact', 'email_manifest')
    
    # Drop trip_order_documents table
    op.drop_table('trip_order_documents')
    
    # Drop internal_contact table
    op.drop_table('internal_contact')


def downgrade():
    # Recreate internal_contact table
    op.create_table('internal_contact',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    
    # Recreate trip_order_documents table
    op.create_table('trip_order_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_order_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=20), nullable=False),
        sa.Column('document_data', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_order_id'], ['trip_order.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_trip_order_docs_trip_order', 'trip_order_documents', ['trip_order_id'], unique=False)
    
    # Recreate email preference columns in customer_contact
    op.add_column('customer_contact', sa.Column('email_invoice', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('customer_contact', sa.Column('email_manifest', sa.Boolean(), nullable=True, server_default='true'))
    
    # Recreate email/document columns in trip_order
    op.add_column('trip_order', sa.Column('email_ready', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trip_order', sa.Column('manifest_attached', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trip_order', sa.Column('invoice_attached', sa.Boolean(), nullable=True, server_default='false'))

