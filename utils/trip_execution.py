"""
Trip execution workflow module
Method-based approach for orchestrating trip execution with Redis worker
"""

import json
import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from models import db, Trip, TripOrder, Driver, Vehicle, TripExecution
from utils.timezone import get_est_now
import re

def _is_valid_biotrack_uid(barcode_id):
    """Validate that barcode_id is a standard BioTrack UID (16-digit number)"""
    if not barcode_id:
        return False
    
    # Convert to string and check if it's exactly 16 digits
    barcode_str = str(barcode_id).strip()
    return len(barcode_str) == 16 and barcode_str.isdigit()

def execute_trip_background_job(trip_id):
    """RQ job function - executes trip in background"""
    from app import app
    
    with app.app_context():
        try:
            print(f"=== RQ TRIP EXECUTION STARTED ===")
            print(f"Trip ID: {trip_id}")
            
            # Update execution status to processing
            _update_trip_execution_status(trip_id, 'processing', 'Starting trip execution...')
            
            # Get trip data
            trip = db.session.get(Trip, trip_id)
            if not trip:
                raise Exception(f"Trip {trip_id} not found")
            
            # Get trip orders with sequence
            trip_orders = db.session.query(TripOrder).filter_by(trip_id=trip_id).order_by(TripOrder.sequence_order).all()
            
            if not trip_orders:
                raise Exception("No orders found for trip")
            
            # Get driver and vehicle information
            driver1 = db.session.get(Driver, trip.driver1_id)
            driver2 = db.session.get(Driver, trip.driver2_id)
            vehicle = db.session.get(Vehicle, trip.vehicle_id)
            
            if not driver1 or not driver2 or not vehicle:
                raise Exception("Driver or vehicle information not found")
            
            # Initialize BioTrack API
            from api.biotrack import get_auth_token, post_sublot_bulk_create, post_sublot_move, post_manifest
            from api.leaftrade import get_order_details
            
            # Authenticate with BioTrack
            _update_trip_execution_status(trip_id, 'processing', 'Authenticating with BioTrack API...')
            token = get_auth_token()
            if not token:
                raise Exception("Failed to authenticate with BioTrack API")
            
            # Initialize route optimization
            _update_trip_execution_status(trip_id, 'processing', 'Generating route optimization...')
            route_segments = None
            
            # Check if route data already exists
            if trip.route_data:
                try:
                    route_segments = json.loads(trip.route_data)
                    print(f"Using existing route segments from previous execution attempt")
                except json.JSONDecodeError:
                    print("Failed to parse existing route data, will regenerate")
                    trip.route_data = None
            
            # Generate route segments if needed
            if not route_segments:
                from api.googlemaps_client import GoogleMapsClient
                googlemaps_client = GoogleMapsClient()
                
                # Get trip data for OpenAI routing
                trip_data = {
                    'driver1_name': driver1.name,
                    'driver2_name': driver2.name,
                    'vehicle_name': vehicle.name,
                    'delivery_date': get_est_now().strftime('%Y-%m-%d'),
                    'orders': []
                }
                
                # Extract addresses for OpenAI routing
                addresses = []
                for trip_order in trip_orders:
                    address = trip_order.address or 'Unknown Address'
                    addresses.append(address)
                
                # Generate route segments using Google Maps
                print(f"Generating route segments for {len(addresses)} addresses")
                
                # Prepare delivery date and start time
                delivery_date = trip.delivery_date.strftime('%Y-%m-%d')
                if trip.approximate_start_time:
                    approx_start_time = trip.approximate_start_time.strftime('%Y-%m-%d %I:%M %p')
                else:
                    approx_start_time = f"{delivery_date} 08:00 AM"
                
                route_segments = googlemaps_client.generate_route_segments(addresses, delivery_date, approx_start_time)
                
                # Save route data to trip
                trip.route_data = json.dumps(route_segments)
                db.session.commit()
            
            # Process each order
            _update_trip_execution_status(trip_id, 'processing', 'Processing orders and generating manifests...')
            manifest_results = []
            successful_orders = []
            failed_orders = []
            critical_failures = []
            
            for i, trip_order in enumerate(trip_orders):
                try:
                    _update_trip_execution_status(trip_id, 'processing', f'Processing order {i+1} of {len(trip_orders)}: {trip_order.order_id}')
                    
                    # Get order details from LeafTrade
                    order_details = get_order_details(trip_order.order_id)
                    if not order_details:
                        error_msg = f"Could not retrieve order details for {trip_order.order_id}"
                        print(f"Order processing failed: {error_msg}")
                        trip_order.error_message = error_msg
                        db.session.commit()
                        manifest_results.append({
                            'order_id': trip_order.order_id,
                            'status': 'failed',
                            'error': error_msg
                        })
                        critical_failures.append(error_msg)
                        continue
                    
                    # Process sublot and manifest creation
                    result = _process_order_manifest(trip_order, order_details, token, route_segments)
                    manifest_results.append(result)
                    
                    if result['status'] == 'success':
                        print(f"Order {trip_order.order_id} processed successfully")
                        successful_orders.append(result)
                    elif result['status'] == 'skipped':
                        print(f"Order {trip_order.order_id} skipped: {result.get('message', 'No valid BioTrack UIDs')}")
                        # Don't add to failed_orders or critical_failures for skipped orders
                    else:
                        print(f"Order {trip_order.order_id} failed: {result.get('error', 'Unknown error')}")
                        failed_orders.append(result)
                        if 'critical' in result.get('error', '').lower():
                            critical_failures.append(result['error'])
                    
                except Exception as e:
                    error_msg = f"Error processing order {trip_order.order_id}: {str(e)}"
                    print(error_msg)
                    trip_order.error_message = error_msg
                    db.session.commit()
                    manifest_results.append({
                        'order_id': trip_order.order_id,
                        'status': 'failed',
                        'error': str(e)
                    })
                    critical_failures.append(error_msg)
            
            # Check results and update trip status
            if critical_failures:
                error_details = '; '.join(critical_failures)
                print(f"Critical failures detected: {error_details}")
                execution = db.session.query(TripExecution).filter_by(trip_id=trip_id).first()
                if execution:
                    execution.general_error = error_details
                _update_trip_execution_status(trip_id, 'failed', f'Trip execution failed due to critical errors: {error_details}')
                trip.execution_status = 'failed'
                db.session.commit()
                raise Exception(f"Trip execution failed due to critical errors: {error_details}")
            
            if failed_orders and successful_orders:
                # Partial success
                _update_trip_execution_status(trip_id, 'completed', f'Trip partially completed: {len(successful_orders)} orders succeeded, {len(failed_orders)} failed')
                trip.status = 'partially_completed'
                trip.execution_status = 'completed'
                trip.date_transacted = get_est_now()
                db.session.commit()
            elif failed_orders:
                # All orders failed
                _update_trip_execution_status(trip_id, 'failed', 'All orders failed to process')
                trip.execution_status = 'failed'
                db.session.commit()
                raise Exception("All orders failed to process")
            else:
                # All orders succeeded
                _update_trip_execution_status(trip_id, 'completed', 'Trip execution completed successfully')
                trip.status = 'completed'
                trip.execution_status = 'completed'
                trip.date_transacted = get_est_now()
                db.session.commit()
            
            print(f"=== RQ TRIP EXECUTION COMPLETED ===")
            return {
                'success': True,
                'message': 'Trip execution completed successfully',
                'manifest_results': manifest_results
            }
            
        except Exception as e:
            print(f"=== RQ TRIP EXECUTION FAILED ===")
            db.session.rollback()  # Rollback any pending transaction before querying
            execution = db.session.query(TripExecution).filter_by(trip_id=trip_id).first()
            if execution:
                execution.general_error = str(e)
            _update_trip_execution_status(trip_id, 'failed', f'Execution failed: {str(e)}')
            trip = db.session.get(Trip, trip_id)
            if trip:
                trip.execution_status = 'failed'
            db.session.commit()
            raise e

def _update_trip_execution_status(trip_id, status, progress_message=None):
    """Helper - updates trip execution status in database"""
    execution = db.session.query(TripExecution).filter_by(trip_id=trip_id).first()
    
    if not execution:
        execution = TripExecution(
            trip_id=trip_id,
            status=status,
            progress_message=progress_message
        )
        db.session.add(execution)
        try:
            db.session.commit()
        except IntegrityError:
            # Record already exists (race condition), rollback and retry with update
            db.session.rollback()
            execution = db.session.query(TripExecution).filter_by(trip_id=trip_id).first()
            if execution:
                execution.status = status
                execution.progress_message = progress_message
                execution.updated_at = get_est_now()
                if status in ['completed', 'failed']:
                    execution.completed_at = get_est_now()
                db.session.commit()
    else:
        execution.status = status
        execution.progress_message = progress_message
        execution.updated_at = get_est_now()
        
        if status in ['completed', 'failed']:
            execution.completed_at = get_est_now()
        
        db.session.commit()

def _process_order_manifest(trip_order, order_details, token, route_segments=None):
    """Process individual order manifest creation using original working pattern"""
    try:
        print(f"Processing manifest for order {trip_order.order_id}")
        
        # Extract order data
        order_data = order_details.get('order', {})
        dispensary_location = order_data.get('dispensary_location', {})
        customer = order_data.get('customer', {})
        
        print(f"Order data extracted - Customer: {customer.get('name', 'Unknown')}, Location: {dispensary_location.get('city', 'Unknown')}")
        
        # Get line items for sublot creation (original working pattern)
        line_items = order_details.get('line_items', [])
        sublot_data = []
        invalid_uid_count = 0
        
        for line_item in line_items:
            barcode_id = line_item.get('barcode_id')  # batch_ref from LeafTrade
            quantity = line_item.get('quantity', 1)
            
            # Only process line items with valid BioTrack UIDs (16-digit numbers)
            if barcode_id and _is_valid_biotrack_uid(barcode_id):
                sublot_data.append({
                    'barcodeid': barcode_id,
                    'remove_quantity': str(quantity)
                })
            elif barcode_id:
                invalid_uid_count += 1
                print(f"Skipping invalid BioTrack UID: {barcode_id} (not 16 digits)")
        
        # Log summary of filtered items
        if invalid_uid_count > 0:
            print(f"Filtered out {invalid_uid_count} line items with invalid BioTrack UIDs")
        
        if not sublot_data:
            print(f"Order {trip_order.order_id}: No valid BioTrack UIDs found - skipping order")
            return {
                'order_id': trip_order.order_id,
                'status': 'skipped',
                'message': 'No valid BioTrack UIDs found - order skipped'
            }
        
        # Create sublots for this order (original working pattern)
        print(f"Creating sublot for order {trip_order.order_id}")
        from api.biotrack import post_sublot_bulk_create
        sublot_result = post_sublot_bulk_create(token, sublot_data)
        
        # Check if sublot creation returned an error response
        if isinstance(sublot_result, dict) and not sublot_result.get('success', True):
            error_msg = f"BioTrack sublot creation failed for order {trip_order.order_id}: {sublot_result.get('error', 'Unknown error')} (Code: {sublot_result.get('errorcode', 'Unknown')})"
            print(f"Sublot creation failed: {error_msg}")
            trip_order.error_message = error_msg
            db.session.commit()
            return {
                'order_id': trip_order.order_id,
                'status': 'failed',
                'error': f"BioTrack Error: {sublot_result.get('error', 'Unknown error')} (Code: {sublot_result.get('errorcode', 'Unknown')})"
            }
        
        new_barcode_ids = sublot_result
        if not new_barcode_ids:
            error_msg = f"No barcode IDs returned from sublot creation for order {trip_order.order_id}"
            print(f"Order processing failed: {error_msg}")
            trip_order.error_message = error_msg
            db.session.commit()
            return {
                'order_id': trip_order.order_id,
                'status': 'failed',
                'error': 'No barcode IDs returned from sublot creation'
            }
        
        # Update status to sublotted after successful sublot creation
        trip_order.status = 'sublotted'
        trip_order.error_message = None
        db.session.commit()
        
        # Get room ID from location mapping
        from models import LocationMapping
        dispensary_location_id = order_data.get('dispensary_location', {}).get('id')
        room_id = 'default_room'  # Default fallback
        
        if dispensary_location_id:
            location_mapping = db.session.query(LocationMapping).filter_by(
                leaftrade_dispensary_location_id=dispensary_location_id
            ).first()
            if location_mapping and location_mapping.default_biotrack_room_id:
                room_id = location_mapping.default_biotrack_room_id
            elif trip_order.room_override:
                room_id = trip_order.room_override
        
        # Move sublots to room (original working pattern)
        print(f"Moving sublots to room for order {trip_order.order_id}")
        move_data = []
        for barcode_id in new_barcode_ids:
            move_data.append({
                'barcodeid': barcode_id,
                'room': room_id
            })
        
        from api.biotrack import post_sublot_move
        move_result = post_sublot_move(token, move_data)
        if not move_result:
            error_msg = f"Failed to move sublots to room for order {trip_order.order_id}"
            print(f"Order processing failed: {error_msg}")
            trip_order.error_message = error_msg
            db.session.commit()
            return {
                'order_id': trip_order.order_id,
                'status': 'failed',
                'error': 'Failed to move sublots to room'
            }
        
        # Update status to inventory_moved after successful move
        trip_order.status = 'inventory_moved'
        trip_order.error_message = None
        db.session.commit()
        
        # Get vendor ID from location mapping
        vendor_license = 'default_license'  # Default fallback
        
        if dispensary_location_id:
            location_mapping = db.session.query(LocationMapping).filter_by(
                leaftrade_dispensary_location_id=dispensary_location_id
            ).first()
            if location_mapping and location_mapping.biotrack_vendor_id:
                vendor_license = location_mapping.biotrack_vendor_id
        
        # Create manifest with route data (original working pattern)
        print(f"Creating manifest for order {trip_order.order_id}")
        
        # Get route segment for this order based on sequence
        route_index = trip_order.sequence_order - 1
        route_segment = route_segments[route_index] if route_segments and route_index < len(route_segments) else None
        
        manifest_data = {
            'approximate_departure': route_segment['departure_time'] if route_segment else int(datetime.now().timestamp()),
            'approximate_arrival': route_segment['arrival_time'] if route_segment else int((datetime.now().timestamp() + 3600)),
            'approximate_route': route_segment['route'] if route_segment else f"Route for order {trip_order.order_id}",
            'stop_number': str(trip_order.sequence_order),
            'barcodeid': new_barcode_ids,
            'vendor_license': vendor_license
        }
        
        from api.biotrack import post_manifest
        manifest_result = post_manifest(
            token, 
            manifest_data, 
            [trip_order.trip.driver1.biotrack_id, trip_order.trip.driver2.biotrack_id],
            trip_order.trip.vehicle.biotrack_id
        )
        
        if not manifest_result:
            error_msg = f"Failed to create manifest for order {trip_order.order_id}"
            print(f"Manifest creation failed: {error_msg}")
            trip_order.error_message = error_msg
            db.session.commit()
            return {
                'order_id': trip_order.order_id,
                'status': 'failed',
                'error': 'Failed to create manifest'
            }
        
        # Store manifest ID in database (following reference implementation)
        trip_order.manifest_id = str(manifest_result)
        # Update status to manifested after successful manifest creation
        trip_order.status = 'manifested'
        trip_order.error_message = None
        db.session.commit()
        print(f"Stored manifest ID {manifest_result} for order {trip_order.order_id}")
        
        return {
            'order_id': trip_order.order_id,
            'status': 'success',
            'sublot_ids': new_barcode_ids,
            'manifest_id': manifest_result
        }
        
    except Exception as e:
        error_msg = f"Critical error processing order: {str(e)}"
        trip_order.error_message = error_msg
        db.session.commit()
        return {
            'order_id': trip_order.order_id,
            'status': 'failed',
            'error': error_msg
        }
