"""
Background job functions for report generation
"""
import os
import csv
import time
import logging
from datetime import datetime
from io import StringIO
from flask import current_app
from models import db, ReportJob
from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check

logger = logging.getLogger('utils.report_generation')

def generate_inventory_report_background(job_id, user_id):
    """Background job for inventory report generation"""
    logger.info(f"Starting inventory report generation job {job_id} for user {user_id}")
    
    try:
        # Get the job record
        job = ReportJob.query.filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        # Update job status to processing
        job.status = 'processing'
        job.progress_percentage = 0
        db.session.commit()
        
        # Authenticate with BioTrack
        logger.debug("Authenticating with BioTrack")
        token = get_auth_token()
        if not token:
            raise Exception("Failed to authenticate with BioTrack API")
        
        # Get inventory data
        logger.debug("Fetching inventory data from BioTrack")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            raise Exception("Failed to retrieve inventory data from BioTrack")
        
        job.total_items = len(inventory_data)
        job.progress_percentage = 10
        db.session.commit()
        
        # Get room data for room name lookup
        logger.debug("Fetching room data from BioTrack")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        job.progress_percentage = 20
        db.session.commit()
        
        # Create CSV content
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Item ID (Text)', 'Product Name', 'Quantity', 'Current Room ID (Text)', 
            'Current Room Name', 'Lab Data Available', 'Total %', 'THCA %', 
            'THC %', 'CBDA %', 'CBD %'
        ])
        
        # Process inventory items with progress tracking
        items_processed = 0
        items_with_lab_data = 0
        items_without_lab_data = 0
        start_time = time.time()
        
        logger.info(f"Processing {len(inventory_data)} inventory items for CSV generation")
        
        for i, (item_id, item_info) in enumerate(inventory_data.items()):
            try:
                # Log progress every 50 items
                if i % 50 == 0:
                    elapsed = time.time() - start_time
                    logger.info(f"Processing item {i+1}/{len(inventory_data)} (elapsed: {elapsed:.1f}s)")
                    # Update progress percentage (20% to 90% for processing)
                    progress = 20 + int((i / len(inventory_data)) * 70)
                    job.progress_percentage = progress
                    job.items_processed = i
                    db.session.commit()
                
                # Get room name - use correct field name from BioTrack response
                current_room_id = str(item_info.get('currentroom', ''))
                current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
                
                # Try to get lab data for this item
                barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
                lab_results = None
                
                if barcode_id:
                    try:
                        lab_results = get_inventory_qa_check(token, barcode_id)
                    except Exception as e:
                        logger.warning(f"Error getting lab data for barcode {barcode_id}: {str(e)}")
                        lab_results = None
                
                # Lab data fields
                if lab_results:
                    lab_data_available = 'Yes'
                    total_pct = lab_results.get('total', '')
                    thca_pct = lab_results.get('thca', '')
                    thc_pct = lab_results.get('thc', '')
                    cbda_pct = lab_results.get('cbda', '')
                    cbd_pct = lab_results.get('cbd', '')
                    items_with_lab_data += 1
                else:
                    lab_data_available = 'No'
                    total_pct = ''
                    thca_pct = ''
                    thc_pct = ''
                    cbda_pct = ''
                    cbd_pct = ''
                    items_without_lab_data += 1
                
                # Write row - use correct field names from BioTrack response
                writer.writerow([
                    str(item_id),
                    item_info.get('productname', 'Unknown Product'),
                    item_info.get('remaining_quantity', 0),
                    str(current_room_id),
                    current_room_name,
                    lab_data_available,
                    total_pct,
                    thca_pct,
                    thc_pct,
                    cbda_pct,
                    cbd_pct
                ])
                
                items_processed += 1
                
            except Exception as e:
                logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
                continue
        
        # Save CSV to file
        output.seek(0)
        csv_content = output.getvalue()
        
        # Create storage directory if it doesn't exist
        storage_dir = os.path.join(current_app.root_path, 'storage', 'reports')
        os.makedirs(storage_dir, exist_ok=True)
        
        # Save file
        filename = 'inventory_report_latest.csv'
        file_path = os.path.join(storage_dir, filename)
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Update job with completion details
        job.status = 'completed'
        job.progress_percentage = 100
        job.items_processed = items_processed
        job.file_path = file_path
        job.filename = filename
        job.completed_at = datetime.now()
        db.session.commit()
        
        total_time = time.time() - start_time
        logger.info(f"Completed inventory report generation: {items_processed} items "
                   f"({items_with_lab_data} with lab data, {items_without_lab_data} without), "
                   f"processed in {total_time:.1f}s")
        
        # Clean up old inventory reports
        cleanup_old_reports('inventory')
        
    except Exception as e:
        logger.error(f"Error generating inventory report: {str(e)}")
        # Update job with error
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = datetime.now()
        db.session.commit()

def generate_finished_goods_report_background(job_id, user_id, selected_rooms):
    """Background job for finished goods report generation"""
    logger.info(f"Starting finished goods report generation job {job_id} for user {user_id}")
    
    try:
        # Get the job record
        job = ReportJob.query.filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        # Update job status to processing
        job.status = 'processing'
        job.progress_percentage = 0
        db.session.commit()
        
        # Authenticate with BioTrack
        logger.debug("Authenticating with BioTrack")
        token = get_auth_token()
        if not token:
            raise Exception("Failed to authenticate with BioTrack API")
        
        # Get inventory data
        logger.debug("Fetching inventory data from BioTrack")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            raise Exception("Failed to retrieve inventory data from BioTrack")
        
        # Get room data for room name lookup
        logger.debug("Fetching room data from BioTrack")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Define finished goods inventory types
        finished_goods_types = [22, 23, 24, 25, 28, 34, 35, 36, 37, 38, 39, 45]
        
        # Pre-filter items to reduce processing time
        logger.debug("Pre-filtering inventory items")
        pre_filtered_items = []
        for item_id, item_info in inventory_data.items():
            # Filter by selected rooms
            current_room_id = str(item_info.get('currentroom', ''))
            if selected_rooms and current_room_id not in selected_rooms:
                continue
            
            # Filter by inventory type
            inventory_type = item_info.get('inventorytype')
            if inventory_type not in finished_goods_types:
                continue
            
            pre_filtered_items.append((item_id, item_info))
        
        job.total_items = len(pre_filtered_items)
        job.progress_percentage = 20
        db.session.commit()
        
        logger.info(f"Pre-filtered to {len(pre_filtered_items)} items matching room and type criteria")
        
        # Create CSV content
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Item ID (Text)', 'Product Name', 'Quantity', 'Current Room ID (Text)', 
            'Current Room Name', 'Inventory Type', 'Lab Data Available', 'Total %', 'THCA %', 
            'THC %', 'CBDA %', 'CBD %'
        ])
        
        # Process pre-filtered inventory items
        items_processed = 0
        items_with_lab_data = 0
        items_without_lab_data = 0
        start_time = time.time()
        
        for i, (item_id, item_info) in enumerate(pre_filtered_items):
            try:
                # Log progress every 25 items (smaller batches for finished goods)
                if i % 25 == 0:
                    elapsed = time.time() - start_time
                    logger.info(f"Processing item {i+1}/{len(pre_filtered_items)} (elapsed: {elapsed:.1f}s)")
                    # Update progress percentage (20% to 90% for processing)
                    progress = 20 + int((i / len(pre_filtered_items)) * 70)
                    job.progress_percentage = progress
                    job.items_processed = i
                    db.session.commit()
                
                # Get room name
                current_room_id = str(item_info.get('currentroom', ''))
                current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
                
                # Try to get lab data for this item
                barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
                lab_results = None
                
                if barcode_id:
                    try:
                        lab_results = get_inventory_qa_check(token, barcode_id)
                    except Exception as e:
                        logger.warning(f"Error getting lab data for barcode {barcode_id}: {str(e)}")
                        lab_results = None
                
                # Only include items with lab data (QA passed)
                if not lab_results:
                    items_without_lab_data += 1
                    continue
                
                items_with_lab_data += 1
                
                # Extract lab data
                total_pct = lab_results.get('total', '') if lab_results else ''
                thca_pct = lab_results.get('thca', '') if lab_results else ''
                thc_pct = lab_results.get('thc', '') if lab_results else ''
                cbda_pct = lab_results.get('cbda', '') if lab_results else ''
                cbd_pct = lab_results.get('cbd', '') if lab_results else ''
                
                # Write row - use correct field names from BioTrack response
                writer.writerow([
                    str(item_id),
                    item_info.get('productname', 'Unknown Product'),
                    item_info.get('remaining_quantity', 0),
                    current_room_id,
                    current_room_name,
                    item_info.get('inventorytype'),
                    'Yes',  # Lab data available
                    total_pct,
                    thca_pct,
                    thc_pct,
                    cbda_pct,
                    cbd_pct
                ])
                
                items_processed += 1
                
            except Exception as e:
                logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
                continue
        
        # Save CSV to file
        output.seek(0)
        csv_content = output.getvalue()
        
        # Create storage directory if it doesn't exist
        storage_dir = os.path.join(current_app.root_path, 'storage', 'reports')
        os.makedirs(storage_dir, exist_ok=True)
        
        # Save file
        filename = 'finished_goods_report_latest.csv'
        file_path = os.path.join(storage_dir, filename)
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Update job with completion details
        job.status = 'completed'
        job.progress_percentage = 100
        job.items_processed = items_processed
        job.file_path = file_path
        job.filename = filename
        job.completed_at = datetime.now()
        db.session.commit()
        
        total_time = time.time() - start_time
        logger.info(f"Completed finished goods report generation: {items_processed} items with lab data, "
                   f"{items_without_lab_data} filtered out, processed in {total_time:.1f}s")
        
        # Clean up old finished goods reports
        cleanup_old_reports('finished_goods')
        
    except Exception as e:
        logger.error(f"Error generating finished goods report: {str(e)}")
        # Update job with error
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = datetime.now()
        db.session.commit()

def cleanup_old_reports(report_type):
    """Clean up old reports of the same type when new one completes"""
    try:
        # Find other completed reports of the same type
        old_reports = ReportJob.query.filter(
            ReportJob.report_type == report_type,
            ReportJob.status == 'completed',
            ReportJob.id != ReportJob.query.filter_by(report_type=report_type, status='completed').order_by(ReportJob.completed_at.desc()).first().id
        ).all()
        
        for old_report in old_reports:
            # Delete file if it exists
            if old_report.file_path and os.path.exists(old_report.file_path):
                try:
                    os.remove(old_report.file_path)
                    logger.info(f"Deleted old {report_type} report file: {old_report.file_path}")
                except Exception as e:
                    logger.warning(f"Error deleting old report file {old_report.file_path}: {str(e)}")
            
            # Mark as cleaned up and delete record
            db.session.delete(old_report)
        
        db.session.commit()
        logger.info(f"Cleaned up {len(old_reports)} old {report_type} reports")
        
    except Exception as e:
        logger.error(f"Error cleaning up old {report_type} reports: {str(e)}")
        db.session.rollback()
