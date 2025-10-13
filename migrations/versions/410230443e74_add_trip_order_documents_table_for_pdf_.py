"""add_trip_order_documents_table_for_pdf_storage

Revision ID: 410230443e74
Revises: 589e63de7d15
Create Date: 2025-09-01 11:51:25.935205

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '410230443e74'
down_revision = '589e63de7d15'
branch_labels = None
depends_on = None


def upgrade():
    # Create trip_order_documents table
    op.create_table('trip_order_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_order_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=20), nullable=False),
        sa.Column('document_data', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_order_id'], ['trip_order.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trip_order_id', 'document_type', name='unique_trip_order_document_type')
    )
    op.create_index('idx_trip_order_docs_trip_order', 'trip_order_documents', ['trip_order_id'], unique=False)


def downgrade():
    # Drop trip_order_documents table
    op.drop_index('idx_trip_order_docs_trip_order', table_name='trip_order_documents')
    op.drop_table('trip_order_documents')
