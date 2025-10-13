"""
Document service for PDF compression and storage
"""
import gzip
import logging
from models import db, TripOrder, TripOrderDocument

logger = logging.getLogger(__name__)

class DocumentService:
    """Simple document upload, compression, and storage"""
    
    def compress_pdf(self, pdf_data: bytes) -> bytes:
        """Compress PDF data using gzip"""
        return gzip.compress(pdf_data, compresslevel=9)
    
    def decompress_pdf(self, compressed_data: bytes) -> bytes:
        """Decompress PDF data"""
        return gzip.decompress(compressed_data)
    
    def store_document(self, trip_order_id: int, document_type: str, 
                      file_data: bytes) -> bool:
        """Store compressed document in database"""
        try:
            compressed_data = self.compress_pdf(file_data)
            
            # Check if document already exists and update it
            existing_doc = TripOrderDocument.query.filter_by(
                trip_order_id=trip_order_id,
                document_type=document_type
            ).first()
            
            if existing_doc:
                existing_doc.document_data = compressed_data
                existing_doc.uploaded_at = db.func.now()
            else:
                doc = TripOrderDocument(
                    trip_order_id=trip_order_id,
                    document_type=document_type,
                    document_data=compressed_data
                )
                db.session.add(doc)
            
            # Update trip order status
            trip_order = TripOrder.query.get(trip_order_id)
            if document_type == 'manifest':
                trip_order.manifest_attached = True
            elif document_type == 'invoice':
                trip_order.invoice_attached = True
            
            # Check if email ready
            if trip_order.manifest_attached and trip_order.invoice_attached:
                trip_order.email_ready = True
            
            db.session.commit()
            logger.info(f"Document {document_type} stored for trip_order {trip_order_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store document: {e}")
            return False
    
    def get_document(self, trip_order_id: int, document_type: str) -> bytes:
        """Get decompressed document"""
        doc = TripOrderDocument.query.filter_by(
            trip_order_id=trip_order_id, 
            document_type=document_type
        ).first()
        if doc:
            return self.decompress_pdf(doc.document_data)
        return None
    
    def delete_document(self, trip_order_id: int, document_type: str) -> bool:
        """Delete document and update trip order status"""
        try:
            doc = TripOrderDocument.query.filter_by(
                trip_order_id=trip_order_id,
                document_type=document_type
            ).first()
            
            if doc:
                db.session.delete(doc)
                
                # Update trip order status
                trip_order = TripOrder.query.get(trip_order_id)
                if document_type == 'manifest':
                    trip_order.manifest_attached = False
                elif document_type == 'invoice':
                    trip_order.invoice_attached = False
                
                # Update email ready status
                trip_order.email_ready = False
                
                db.session.commit()
                logger.info(f"Document {document_type} deleted for trip_order {trip_order_id}")
                return True
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete document: {e}")
            return False
