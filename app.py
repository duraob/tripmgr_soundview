from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import logging
import time
from datetime import datetime, UTC, timedelta, timezone
from utils.timezone import get_est_now
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Training Mode Functions
def get_training_mode():
    """Get training mode from environment variable, default to training (1)"""
    return os.getenv('BIOTRACK_TRAINING_MODE', '1')

def is_training_mode():
    """Check if currently in training mode"""
    return get_training_mode() == '1'

# Configure comprehensive logging for production
def setup_logging():
    """Configure production-ready logging with rotating files and structured format"""
    
    import logging.handlers
    import json
    from datetime import datetime
    
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # JSON formatter for structured logging
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'timestamp': get_est_now().isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'function': record.funcName,
                'line': record.lineno,
                'message': record.getMessage()
            }
            
            # Add exception info if present
            if record.exc_info:
                log_entry['exception'] = self.formatException(record.exc_info)
            
            # Add extra fields if present
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            return json.dumps(log_entry)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Production default
    
    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create rotating file handlers
    # Error logs - 10MB files, keep 10 files
    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'error.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    
    # Info logs - 10MB files, keep 10 files
    info_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'info.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(JSONFormatter())
    
    # Debug logs - 10MB files, keep 5 files (debug logs can be larger)
    debug_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'debug.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(JSONFormatter())
    
    # Console handler for development (only if DEBUG mode)
    if os.getenv('FLASK_DEBUG', 'False').lower() == 'true':
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Add file handlers to root logger
    root_logger.addHandler(error_handler)
    root_logger.addHandler(info_handler)
    root_logger.addHandler(debug_handler)
    
    # Set specific loggers to appropriate levels
    loggers_config = {
        'api.biotrack': logging.INFO,
        'api.leaftrade': logging.INFO,
        'api.openai_client': logging.INFO,
        'api.email_service': logging.INFO,
        'flask': logging.WARNING,  # Reduce Flask noise in production
        'werkzeug': logging.WARNING,  # Reduce Werkzeug noise in production
        'sqlalchemy.engine': logging.WARNING,  # Reduce SQL noise in production
        'sqlalchemy.pool': logging.WARNING,
        'sqlalchemy.dialects': logging.WARNING,
        'sqlalchemy.orm': logging.WARNING
    }
    
    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True
    
    # Create app logger
    app_logger = logging.getLogger('app')
    app_logger.setLevel(logging.INFO)
    
    # Log startup information
    app_logger.info("Production logging configured successfully", extra={
        'extra_fields': {
            'log_dir': log_dir,
            'rotation_size_mb': 10,
            'error_backup_count': 10,
            'info_backup_count': 10,
            'debug_backup_count': 5,
            'flask_debug': os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        }
    })

# Setup logging
setup_logging()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Import models and get db instance
from models import db, User, Trip, Order, TripOrder, Driver, Vehicle, Vendor, Room, LocationMapping, Customer, CustomerContact, InternalContact, GlobalPreference

# Initialize extensions
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)

# Context processor to make training mode available to all templates
@app.context_processor
def inject_training_mode():
    """Inject training mode status into all templates"""
    return {
        'training_mode': get_training_mode(),
        'is_training_mode': is_training_mode()
    }

# Custom Jinja2 filters for template formatting
@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object"""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

@app.template_filter('datetime_from_timestamp')
def datetime_from_timestamp_filter(timestamp, format_str='%Y-%m-%d %H:%M'):
    """Convert Unix timestamp to formatted datetime string in EST"""
    if not timestamp:
        return ''
    try:
        # Create UTC datetime from timestamp
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        # Convert to EST for display
        from utils.timezone import convert_utc_to_est
        est_dt = convert_utc_to_est(dt)
        return est_dt.strftime(format_str)
    except (ValueError, TypeError):
        return ''

@app.template_filter('nl2br')
def nl2br_filter(text):
    """Convert newlines to HTML line breaks"""
    if not text:
        return ''
    return text.replace('\n', '<br>')
login_manager.login_view = 'login'

# Initialize database with app context
with app.app_context():
    db.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Routes
@app.route('/')
@login_required
def dashboard():
    """Redirect to trips page - main landing page"""
    return redirect(url_for('trips'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = db.session.query(User).filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Account is inactive. Please contact an administrator.')
                return render_template('login.html')
            
            login_user(user)
            return redirect(url_for('trips'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users():
    """User management page - admin only"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('trips'))
    
    users = db.session.query(User).order_by(User.created_at.desc()).all()
    return render_template('users.html', users=users)

@app.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    """Create new user - admin only"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('trips'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required')
            return render_template('new_user.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long')
            return render_template('new_user.html')
        
        # Check if user already exists
        existing_user = db.session.query(User).filter_by(username=username).first()
        if existing_user:
            flash('Username already exists')
            return render_template('new_user.html')
        
        existing_email = db.session.query(User).filter_by(email=email).first()
        if existing_email:
            flash('Email already exists')
            return render_template('new_user.html')
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('User created successfully')
        return redirect(url_for('users'))
    
    return render_template('new_user.html')

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit user - admin only"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('trips'))
    
    user = db.session.query(User).get_or_404(user_id)
    
    if request.method == 'POST':
        email = request.form.get('email')
        role = request.form.get('role')
        is_active = request.form.get('is_active') == 'on'
        new_password = request.form.get('new_password')
        
        # Validation
        if not email:
            flash('Email is required')
            return render_template('edit_user.html', user=user)
        
        # Check if email is already taken by another user
        existing_email = db.session.query(User).filter_by(email=email).first()
        if existing_email and existing_email.id != user.id:
            flash('Email already exists')
            return render_template('edit_user.html', user=user)
        
        # Update user
        user.email = email
        user.role = role
        user.is_active = is_active
        
        # Update password if provided
        if new_password:
            if len(new_password) < 6:
                flash('Password must be at least 6 characters long')
                return render_template('edit_user.html', user=user)
            user.password_hash = generate_password_hash(new_password)
        
        db.session.commit()
        flash('User updated successfully')
        return redirect(url_for('users'))
    
    return render_template('edit_user.html', user=user)

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete user - admin only"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('trips'))
    
    user = db.session.query(User).get_or_404(user_id)
    
    # Prevent deleting self
    if user.id == current_user.id:
        flash('Cannot delete your own account')
        return redirect(url_for('users'))
    
    # Prevent deleting the last admin
    if user.role == 'admin':
        admin_count = db.session.query(User).filter_by(role='admin', is_active=True).count()
        if admin_count <= 1:
            flash('Cannot delete the last admin user')
            return redirect(url_for('users'))
    
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully')
    return redirect(url_for('users'))

@app.route('/trips')
@login_required
def trips():
    """Trips listing page"""
    return render_template('trips.html')

@app.route('/trips/<int:trip_id>')
@login_required
def trip_detail(trip_id):
    """Trip detail page"""
    trip = Trip.query.get_or_404(trip_id)
    return render_template('trip_detail.html', trip=trip)

@app.route('/trips/new', methods=['GET', 'POST'])
@login_required
def new_trip():
    """Create new trip"""
    logger = logging.getLogger('app.trips.new')
    
    if request.method == 'POST':
        logger.info("Creating new trip")
        try:
            data = request.get_json()
            logger.debug(f"Received trip data: {data}")
            
            # Comprehensive backend validation
            validation_result = validate_trip_data_backend(data)
            if not validation_result['is_valid']:
                logger.warning(f"Trip validation failed: {validation_result['message']}")
                return jsonify({'error': validation_result['message']}), 400
            
            logger.debug("Backend validation passed")
            
            # Get driver database IDs from biotrack_ids
            driver1 = db.session.query(Driver).filter_by(biotrack_id=data['driver1_id']).first()
            driver2 = db.session.query(Driver).filter_by(biotrack_id=data['driver2_id']).first() if data['driver2_id'] else None
            
            # Get vehicle database ID from biotrack_id
            vehicle = db.session.query(Vehicle).filter_by(biotrack_id=str(data['vehicle_id'])).first()
            
            # Parse date and time with DST handling
            delivery_date = datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
            from utils.timezone import create_est_datetime_with_dst
            approximate_start_time = create_est_datetime_with_dst(delivery_date, data['approximate_start_time'])
            
            # Create new trip
            trip = Trip(
                driver1_id=driver1.id,
                driver2_id=driver2.id if driver2 else None,
                vehicle_id=vehicle.id,
                delivery_date=delivery_date,
                approximate_start_time=approximate_start_time,
                created_by=current_user.id,
                status='pending',
                date_created=get_est_now()
            )
            
            logger.debug(f"Created trip object: driver1={data['driver1_id']}, driver2={data['driver2_id']}, vehicle={data['vehicle_id']}")
            
            db.session.add(trip)
            db.session.flush()  # Get the trip ID
            
            logger.debug(f"Trip ID generated: {trip.id}")
            
            # Add trip orders with sequence
            for i, order_data in enumerate(data['orders']):
                # Get order details to find dispensary location and vendor
                vendor = None
                try:
                    from api.leaftrade import get_order_details
                    order_details = get_order_details(order_data['order_id'])
                    if order_details:
                        # Extract dispensary location ID
                        dispensary_location_id = order_details.get('order', {}).get('dispensary_location', {}).get('id')
                        if dispensary_location_id:
                            # Find location mapping
                            location_mapping = db.session.query(LocationMapping).filter_by(
                                leaftrade_dispensary_location_id=dispensary_location_id
                            ).first()
                            
                            if location_mapping:
                                # Find vendor through location mapping
                                vendor = db.session.query(Vendor).filter_by(
                                    biotrack_vendor_id=location_mapping.biotrack_vendor_id
                                ).first()
                                logger.debug(f"Found vendor {vendor.name if vendor else 'None'} for order {order_data['order_id']}")
                            else:
                                logger.warning(f"No location mapping found for dispensary location {dispensary_location_id}")
                        else:
                            logger.warning(f"No dispensary location ID found for order {order_data['order_id']}")
                    else:
                        logger.warning(f"Could not get order details for {order_data['order_id']}")
                except Exception as e:
                    logger.error(f"Error getting vendor for order {order_data['order_id']}: {str(e)}")
                
                trip_order = TripOrder(
                    trip_id=trip.id,
                    order_id=order_data['order_id'],
                    sequence_order=i + 1,
                    room_override=order_data.get('room_override'),
                    address=order_data.get('customer_location'),
                    vendor_id=vendor.id if vendor else None
                )
                db.session.add(trip_order)
                logger.debug(f"Added trip order {i+1}: {order_data['order_id']} with vendor {vendor.name if vendor else 'None'}")
            
            db.session.commit()
            logger.info(f"Successfully created trip {trip.id} with {len(data['orders'])} orders")
            
            return jsonify({
                'success': True,
                'trip_id': trip.id,
                'message': 'Trip created successfully'
            })
            
        except Exception as e:
            logger.error(f"Exception creating trip: {str(e)}", exc_info=True)
            db.session.rollback()
            return jsonify({'error': f'Error creating trip: {str(e)}'}), 500
    
    logger.debug("Rendering new trip template")
    return render_template('new_trip.html')

def validate_trip_data_backend(data):
    """
    Comprehensive backend validation for trip data
    Returns: {'is_valid': bool, 'message': str}
    """
    logger = logging.getLogger('app.validation')
    
    # Validation 1: Check required fields
    required_fields = ['driver1_id', 'driver2_id', 'vehicle_id', 'orders', 'delivery_date', 'approximate_start_time']
    for field in required_fields:
        if field not in data:
            return {
                'is_valid': False,
                'message': f'Missing required field: {field}'
            }
    
    # Validation 2: Check data types
    try:
        # Driver IDs are BioTrack IDs (strings), vehicle ID is integer
        driver1_id = data['driver1_id']
        driver2_id = data['driver2_id'] if data['driver2_id'] else None
        vehicle_id = int(data['vehicle_id'])
        
        # Validate that driver IDs are non-empty strings
        if not driver1_id or not isinstance(driver1_id, str):
            return {
                'is_valid': False,
                'message': 'Driver 1 ID must be a valid BioTrack ID'
            }
        if driver2_id and not isinstance(driver2_id, str):
            return {
                'is_valid': False,
                'message': 'Driver 2 ID must be a valid BioTrack ID'
            }
    except (ValueError, TypeError):
        return {
            'is_valid': False,
            'message': 'Vehicle ID must be a valid integer'
        }
    
    # Validation 3: Validate date and time formats
    try:
        delivery_date = datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
        approximate_start_time = datetime.strptime(data['approximate_start_time'], '%H:%M').time()
    except (ValueError, TypeError):
        return {
            'is_valid': False,
            'message': 'Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time.'
        }
    
    # Validation 4: Check if orders list is provided and not empty
    if not isinstance(data['orders'], list) or len(data['orders']) == 0:
        return {
            'is_valid': False,
            'message': 'At least one order must be selected for the trip'
        }
    
    # Validation 5: Check for duplicate drivers (only if driver2 is selected)
    if driver2_id and driver1_id == driver2_id:
        return {
            'is_valid': False,
            'message': 'Driver 1 and Driver 2 must be different'
        }
    
    # Validation 6: Verify drivers exist in database (look up by biotrack_id)
    driver1 = db.session.query(Driver).filter_by(biotrack_id=driver1_id).first()
    driver2 = db.session.query(Driver).filter_by(biotrack_id=driver2_id).first() if driver2_id else None
    if not driver1:
        return {
            'is_valid': False,
            'message': 'Driver 1 does not exist in the system'
        }
    if driver2_id and not driver2:
        return {
            'is_valid': False,
            'message': 'Driver 2 does not exist in the system'
        }
    
    # Validation 7: Verify vehicle exists in database (look up by biotrack_id)
    vehicle = db.session.query(Vehicle).filter_by(biotrack_id=str(vehicle_id)).first()
    if not vehicle:
        return {
            'is_valid': False,
            'message': 'Selected vehicle does not exist in the system'
        }
    
    # Validation 8: Check orders structure and validate each order
    order_ids = []
    for i, order_data in enumerate(data['orders']):
        # Check order structure
        if not isinstance(order_data, dict) or 'order_id' not in order_data:
            return {
                'is_valid': False,
                'message': f'Invalid order data structure at position {i+1}'
            }
        
        # Check for duplicate order IDs
        order_id = order_data['order_id']
        if order_id in order_ids:
            return {
                'is_valid': False,
                'message': f'Duplicate order ID found: {order_id}'
            }
        order_ids.append(order_id)
        
        # Verify order exists (this would need to be implemented based on your order data source)
        # For now, we'll assume orders exist if they're provided
        logger.debug(f"Validating order {order_id}")
    
    # Validation 9: Check sequential order sequence (if sequence_order is provided)
    # This assumes the frontend sends orders in the correct sequence
    # If you want to validate sequence_order field specifically, add that logic here
    
    # Validation 10: Check for reasonable limits
    if len(data['orders']) > 20:  # Arbitrary limit, adjust as needed
        return {
            'is_valid': False,
            'message': 'Trip cannot contain more than 20 orders'
        }
    
    logger.info("Backend validation passed successfully")
    return {
        'is_valid': True,
        'message': 'Validation passed'
    }

@app.route('/trips/<int:trip_id>/execute', methods=['POST'])
@login_required
def execute_trip(trip_id):
    """Execute trip - enqueue background job for manifest creation"""
    logger = logging.getLogger('app.execute_trip')
    
    try:
        trip = Trip.query.get_or_404(trip_id)
        
        if trip.status == 'completed':
            return jsonify({'error': 'Trip is not in pending or validated status'}), 400
        
        if trip.execution_status == 'processing':
            return jsonify({'error': 'Trip is already being processed'}), 400
        
        # Get trip orders with sequence
        trip_orders = db.session.query(TripOrder).filter_by(trip_id=trip_id).all()
        
        if not trip_orders:
            return jsonify({'error': 'No orders found for trip'}), 400
        
        # Get driver and vehicle information
        driver1 = db.session.get(Driver, trip.driver1_id)
        driver2 = db.session.get(Driver, trip.driver2_id)
        vehicle = db.session.get(Vehicle, trip.vehicle_id)
        
        if not driver1 or not driver2 or not vehicle:
            return jsonify({'error': 'Driver or vehicle information not found'}), 400
        
        # Enqueue background job
        from utils.task_queue import enqueue_trip_execution
        job_id = enqueue_trip_execution(trip_id)
        
        # Update trip execution status
        trip.execution_status = 'processing'
        db.session.commit()
        
        logger.info(f"Trip {trip_id} execution enqueued with job ID: {job_id}")
        
        return jsonify({
            'success': True,
            'message': 'Trip execution started in background',
            'job_id': job_id,
            'redirect_url': f'/trips/{trip_id}/progress'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error in execute_trip: {str(e)}")
        return jsonify({'error': f'Error executing trip: {str(e)}'}), 500

@app.route('/api/trips/<int:trip_id>/execution-status', methods=['GET'])
@login_required
def get_trip_execution_status(trip_id):
    """Get trip execution status"""
    try:
        trip = Trip.query.get_or_404(trip_id)
        execution = db.session.query(TripExecution).filter_by(trip_id=trip_id).first()
        
        if not execution:
            return jsonify({
                'trip_id': trip_id,
                'execution_status': 'pending',
                'progress_percentage': 0,
                'progress_message': 'Trip execution not started',
                'created_at': trip.date_created.isoformat() if trip.date_created else None
            })
        
        # Calculate progress percentage based on status
        if execution.status == 'completed':
            progress_percentage = 100
        elif execution.status == 'failed':
            progress_percentage = 0
        elif execution.status == 'processing':
            # Calculate progress based on time elapsed
            elapsed_seconds = (get_est_now() - execution.created_at).total_seconds()
            
            # Progress over time: 0-60 seconds = 10-50%, 60+ seconds = 50-90%
            if elapsed_seconds < 60:
                progress_percentage = min(50, 10 + (elapsed_seconds / 60) * 40)
            else:
                progress_percentage = min(90, 50 + ((elapsed_seconds - 60) / 120) * 40)
        else:
            progress_percentage = 0
        
        return jsonify({
            'trip_id': trip_id,
            'execution_status': execution.status,
            'progress_percentage': progress_percentage,
            'progress_message': execution.progress_message,
            'created_at': execution.created_at.isoformat() if execution.created_at else None,
            'updated_at': execution.updated_at.isoformat() if execution.updated_at else None,
            'completed_at': execution.completed_at.isoformat() if execution.completed_at else None
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get trip execution status: {str(e)}'}), 500

@app.route('/trips/<int:trip_id>/progress')
@login_required
def trip_progress(trip_id):
    """Trip execution progress page"""
    trip = Trip.query.get_or_404(trip_id)
    return render_template('trip_progress.html', trip=trip)

@app.route('/api/error-logs', methods=['GET'])
@login_required
def get_error_logs():
    """Get recent error logs for display to users"""
    logger = logging.getLogger('app.get_error_logs')
    
    try:
        # Read the error log file
        log_file = 'logs/error.log'
        if not os.path.exists(log_file):
            return jsonify({'success': False, 'error': 'No error logs found'})
        
        logs = []
        with open(log_file, 'r') as f:
            # Read last 50 lines and parse JSON
            lines = f.readlines()
            recent_lines = lines[-50:]  # Last 50 lines
            
            for line in lines[-20:]:  # Last 20 lines for display
                line = line.strip()
                if line:
                    try:
                        log_entry = json.loads(line)
                        # Only include BioTrack API errors
                        if log_entry.get('logger') == 'api.biotrack':
                            logs.append({
                                'timestamp': log_entry.get('timestamp', ''),
                                'logger': log_entry.get('logger', ''),
                                'function': log_entry.get('function', ''),
                                'message': log_entry.get('message', '')
                            })
                    except json.JSONDecodeError:
                        continue
        
        # Return logs in reverse chronological order
        logs.reverse()
        
        return jsonify({
            'success': True,
            'logs': logs[:10]  # Return last 10 BioTrack errors
        })
        
    except Exception as e:
        logger.error(f"Error reading error logs: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to read error logs'}), 500

@app.route('/trips/<int:trip_id>/toggle-status', methods=['POST'])
@login_required
def toggle_trip_status(trip_id):
    """Toggle trip status between pending and completed"""
    logger = logging.getLogger('app.toggle_trip_status')
    
    try:
        trip = Trip.query.get_or_404(trip_id)
        
        # Get the new status from request
        data = request.get_json()
        new_status = data.get('new_status')
        
        if new_status not in ['pending', 'completed', 'validated']:
            return jsonify({'error': 'Invalid status. Must be "pending", "validated" or "completed"'}), 400
        
        # Update trip status
        old_status = trip.status
        trip.status = new_status
        
        # Commit to database
        db.session.commit()
        
        logger.info(f"Trip {trip_id} status changed from {old_status} to {new_status}")
        
        return jsonify({
            'success': True, 
            'message': f'Trip status updated from {old_status} to {new_status}',
            'old_status': old_status,
            'new_status': new_status
        })
        
    except Exception as e:
        logger.error(f"Trip status toggle error: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'Trip status toggle failed: {str(e)}'}), 500


@app.route('/api/orders')
@login_required
def get_orders():
    """API endpoint to get orders from LeafTrade"""
    logger = logging.getLogger('app.api.orders')
    logger.info(f"Fetching orders with status: {request.args.get('status', 'approved')}")
    
    try:
        from api.leaftrade import get_orders as leaftrade_get_orders
        
        # Get status from query parameter, default to 'approved'
        status = request.args.get('status', 'approved')
        logger.debug(f"Requested order status: {status}")
        
        # Fetch orders from LeafTrade
        logger.debug("Calling LeafTrade API to fetch orders")
        orders_data = leaftrade_get_orders(status=status)
        
        if orders_data is None:
            logger.error("LeafTrade API returned None - no orders data")
            return jsonify({'error': 'Failed to fetch orders from LeafTrade'}), 500
        
        # Convert dictionary to array format expected by frontend
        orders_array = []
        if isinstance(orders_data, dict):
            for order_id, order_info in orders_data.items():
                order_array_item = {
                    'id': order_id,
                    'customer_name': order_info.get('customer_name', 'Unknown Customer'),
                    'customer_location': order_info.get('customer_location', 'Unknown Location'),
                    'delivery_date': order_info.get('delivery_date', 'Not specified'),
                    'dispensary_id': order_info.get('dispensary_id')
                }
                orders_array.append(order_array_item)
        
        logger.info(f"Successfully fetched and formatted {len(orders_array)} orders for frontend")
        return jsonify({'orders': orders_array})
        
    except Exception as e:
        logger.error(f"Exception in get_orders: {str(e)}", exc_info=True)
        # Fallback to mock data for testing
        logger.info("Falling back to mock order data for testing")
        mock_orders = [
            {
                'id': '1043337',
                'customer_name': 'Budr - Danbury MILL PLAIN RD - MED',
                'customer_location': 'Budr - Danbury MILL PLAIN RD - MED - 2025-08-01',
                'delivery_date': '2025-08-01',
                'dispensary_id': '1280',
            }
        ]
        return jsonify({'orders': mock_orders})

@app.route('/api/orders/<order_id>/details')
@login_required
def get_order_details(order_id):
    """API endpoint to get detailed order information including line items from LeafTrade"""
    logger = logging.getLogger('app.api.order_details')
    logger.info(f"Fetching order details for order: {order_id}")
    
    try:
        from api.leaftrade import get_order_details as leaftrade_get_order_details
        
        # Fetch order details from LeafTrade
        logger.debug(f"Calling LeafTrade API to fetch order details for {order_id}")
        order_details = leaftrade_get_order_details(order_id)
        
        if order_details is None:
            logger.error(f"LeafTrade API returned None for order {order_id}")
            return jsonify({'error': 'Failed to fetch order details from LeafTrade'}), 500
        
        logger.info(f"Successfully retrieved order details for {order_id}")
        return jsonify(order_details)
        
    except Exception as e:
        logger.error(f"Exception in get_order_details: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to fetch order details'}), 500

@app.route('/api/trips')
@login_required
def get_trips():
    """API endpoint to get trips with all related data for sorting"""
    logger = logging.getLogger('app.api.trips')
    logger.info("Fetching trips with related data")
    
    try:
        # Get trips with all related data for sorting
        trips = db.session.query(Trip).options(
            db.joinedload(Trip.driver1),
            db.joinedload(Trip.driver2),
            db.joinedload(Trip.vehicle),
            db.joinedload(Trip.trip_orders)
        ).order_by(Trip.date_created.desc()).all()
        
        # Convert to JSON-serializable format
        trips_data = []
        for trip in trips:
            trip_dict = {
                'id': trip.id,
                'status': trip.status,
                'date_created': trip.date_created.isoformat() if trip.date_created else None,
                'date_transacted': trip.date_transacted.isoformat() if trip.date_transacted else None,
                'delivery_date': trip.delivery_date.isoformat() if trip.delivery_date else None,
                'approximate_start_time': trip.approximate_start_time.isoformat() if trip.approximate_start_time else None,
                'driver1': {
                    'id': trip.driver1.id,
                    'name': trip.driver1.name,
                    'biotrack_id': trip.driver1.biotrack_id
                } if trip.driver1 else None,
                'driver2': {
                    'id': trip.driver2.id,
                    'name': trip.driver2.name,
                    'biotrack_id': trip.driver2.biotrack_id
                } if trip.driver2 else None,
                'vehicle': {
                    'id': trip.vehicle.id,
                    'name': trip.vehicle.name,
                    'biotrack_id': trip.vehicle.biotrack_id
                } if trip.vehicle else None,
                'trip_orders': [
                    {
                        'id': to.id,
                        'order_id': to.order_id,
                        'sequence_order': to.sequence_order,
                        'room_override': to.room_override,
                        'address': to.address
                    } for to in trip.trip_orders
                ]
            }
            trips_data.append(trip_dict)
        
        logger.info(f"Successfully fetched {len(trips_data)} trips")
        return jsonify({'trips': trips_data})
        
    except Exception as e:
        logger.error(f"Exception in get_trips: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to fetch trips'}), 500

@app.route('/config')
@login_required
def config():
    """Configuration page for managing API data refresh"""
    return render_template('config.html')

@app.route('/api/drivers')
@login_required
def get_drivers():
    """API endpoint to get drivers from local cache only"""
    logger = logging.getLogger('app.api.drivers')
    logger.info("Fetching drivers from local cache")
    
    try:
        # Get cached drivers from database - handle both boolean and integer values
        cached_drivers = db.session.query(Driver).filter(Driver.is_active.is_(True)).all()
        drivers_array = []
        for driver in cached_drivers:
            drivers_array.append({
                'id': driver.biotrack_id,
                'name': driver.name,
                'is_active': driver.is_active
            })
        
        logger.info(f"Returning {len(drivers_array)} cached drivers")
        
        # If no cached drivers, provide mock data for testing
        if len(drivers_array) == 0:
            logger.info("No cached drivers found, providing mock data for testing")
            mock_drivers = [
                {'id': '1', 'name': 'John Smith', 'is_active': True},
                {'id': '2', 'name': 'Jane Doe', 'is_active': True},
                {'id': '3', 'name': 'Mike Johnson', 'is_active': True}
            ]
            return jsonify({'drivers': mock_drivers})
        
        return jsonify({'drivers': drivers_array})
        
    except Exception as e:
        logger.error(f"Exception in get_drivers: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to fetch drivers from cache'}), 500

@app.route('/api/drivers/refresh', methods=['POST'])
@login_required
def refresh_drivers():
    """API endpoint to refresh drivers from BioTrack"""
    logger = logging.getLogger('app.api.drivers.refresh')
    logger.info("Refreshing drivers from BioTrack")
    
    try:
        from api.biotrack import get_auth_token, get_driver_info
        
        # Get authentication token
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to get authentication token from BioTrack")
            return jsonify({'error': 'Failed to authenticate with BioTrack'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Fetch drivers from BioTrack
        logger.debug("Calling BioTrack API to fetch drivers")
        drivers_data = get_driver_info(token)
        
        if drivers_data is None:
            logger.error("BioTrack API returned None - no drivers data")
            return jsonify({'error': 'Failed to fetch drivers from BioTrack'}), 500
        
        # Update local database with fresh data
        for driver_id, driver_info in drivers_data.items():
            existing_driver = db.session.query(Driver).filter_by(biotrack_id=driver_id).first()
            if existing_driver:
                existing_driver.name = driver_info['name']
                existing_driver.is_active = bool(driver_info['is_active'])
            else:
                new_driver = Driver(
                    biotrack_id=driver_id,
                    name=driver_info['name'],
                    is_active=bool(driver_info['is_active'])
                )
                db.session.add(new_driver)
        
        db.session.commit()
        
        # Convert to array format for response
        drivers_array = []
        for driver_id, driver_info in drivers_data.items():
            drivers_array.append({
                'id': driver_id,
                'name': driver_info['name'],
                'is_active': driver_info['is_active']
            })
        
        logger.info(f"Successfully refreshed and cached {len(drivers_array)} drivers from BioTrack")
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(drivers_array)} drivers',
            'drivers': drivers_array
        })
        
    except Exception as e:
        logger.error(f"Exception in refresh_drivers: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to refresh drivers from BioTrack'}), 500

@app.route('/api/vehicles')
@login_required
def get_vehicles():
    """API endpoint to get vehicles from local cache only"""
    logger = logging.getLogger('app.api.vehicles')
    logger.info("Fetching vehicles from local cache")
    
    try:
        # Get cached vehicles from database - handle both boolean and integer values
        cached_vehicles = db.session.query(Vehicle).filter(Vehicle.is_active.is_(True)).all()
        vehicles_array = []
        for vehicle in cached_vehicles:
            vehicles_array.append({
                'id': vehicle.biotrack_id,
                'name': vehicle.name,
                'is_active': vehicle.is_active
            })
        
        logger.info(f"Returning {len(vehicles_array)} cached vehicles")
        
        # If no cached vehicles, provide mock data for testing
        if len(vehicles_array) == 0:
            logger.info("No cached vehicles found, providing mock data for testing")
            mock_vehicles = [
                {'id': '1', 'name': 'Van 1', 'is_active': True},
                {'id': '2', 'name': 'Van 2', 'is_active': True},
                {'id': '3', 'name': 'Truck 1', 'is_active': True}
            ]
            return jsonify({'vehicles': mock_vehicles})
        
        return jsonify({'vehicles': vehicles_array})
        
    except Exception as e:
        logger.error(f"Exception in get_vehicles: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to fetch vehicles from cache'}), 500

@app.route('/api/vehicles/refresh', methods=['POST'])
@login_required
def refresh_vehicles():
    """API endpoint to refresh vehicles from BioTrack"""
    logger = logging.getLogger('app.api.vehicles.refresh')
    logger.info("Refreshing vehicles from BioTrack")
    
    try:
        from api.biotrack import get_auth_token, get_vehicle_info
        
        # Get authentication token
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to get authentication token from BioTrack")
            return jsonify({'error': 'Failed to authenticate with BioTrack'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Fetch vehicles from BioTrack
        logger.debug("Calling BioTrack API to fetch vehicles")
        vehicles_data = get_vehicle_info(token)
        
        if vehicles_data is None:
            logger.error("BioTrack API returned None - no vehicles data")
            return jsonify({'error': 'Failed to fetch vehicles from BioTrack'}), 500
        
        # Update local database with fresh data
        for vehicle_id, vehicle_info in vehicles_data.items():
            existing_vehicle = db.session.query(Vehicle).filter_by(biotrack_id=vehicle_id).first()
            if existing_vehicle:
                existing_vehicle.name = vehicle_info['name']
                existing_vehicle.is_active = bool(vehicle_info['is_active'])
            else:
                new_vehicle = Vehicle(
                    biotrack_id=vehicle_id,
                    name=vehicle_info['name'],
                    is_active=bool(vehicle_info['is_active'])
                )
                db.session.add(new_vehicle)
        
        db.session.commit()
        
        # Convert to array format for response
        vehicles_array = []
        for vehicle_id, vehicle_info in vehicles_data.items():
            vehicles_array.append({
                'id': vehicle_id,
                'name': vehicle_info['name'],
                'is_active': vehicle_info['is_active']
            })
        
        logger.info(f"Successfully refreshed and cached {len(vehicles_array)} vehicles from BioTrack")
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(vehicles_array)} vehicles',
            'vehicles': vehicles_array
        })
        
    except Exception as e:
        logger.error(f"Exception in refresh_vehicles: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to refresh vehicles from BioTrack'}), 500

@app.route('/api/locations')
@login_required
def get_locations():
    """API endpoint to get location mappings"""
    try:
        # Get all active location mappings
        mappings = db.session.query(LocationMapping).filter_by(is_active=True).all()
        
        locations = []
        for mapping in mappings:
            locations.append({
                'id': mapping.id,
                'leaftrade_location_id': mapping.leaftrade_location_id,
                'biotrack_vendor_id': mapping.biotrack_vendor_id,
                'default_biotrack_room_id': mapping.default_biotrack_room_id,
                'location_name': mapping.location_name,
                'vendor_name': mapping.vendor_name,
                'room_name': mapping.room_name
            })
        
        return jsonify({'locations': locations})
        
    except Exception as e:
        return jsonify({'error': f'Error fetching locations: {str(e)}'}), 500

@app.route('/api/rooms')
@login_required
def get_rooms():
    """API endpoint to get rooms from BioTrack (cached only)"""
    logger = logging.getLogger('app.api.rooms')
    logger.info("Fetching rooms from local cache")
    
    try:
        from models import Room
        
        # Get rooms from local database only - no automatic API calls
        # Use is_(True) to handle both boolean and integer values
        rooms = db.session.query(Room).filter(Room.is_active.is_(True)).all()
        
        logger.info(f"Found {len(rooms)} active rooms in database")
        
        # Convert to array format
        rooms_array = []
        for room in rooms:
            rooms_array.append({
                'id': room.biotrack_room_id,
                'biotrack_room_id': room.biotrack_room_id,
                'name': room.name,
                'is_active': room.is_active
            })
        
        logger.info(f"Returning {len(rooms_array)} rooms to frontend")
        return jsonify({'rooms': rooms_array})
        
    except Exception as e:
        logger.error(f"Exception in get_rooms: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error fetching rooms: {str(e)}'}), 500

@app.route('/api/rooms/refresh', methods=['POST'])
@login_required
def refresh_rooms():
    """API endpoint to refresh rooms from BioTrack"""
    try:
        from api.biotrack import get_auth_token, get_room_info
        from models import Room, APIRefreshLog
        
        logger = logging.getLogger('app.refresh_rooms')
        logger.info("Starting rooms refresh from BioTrack")
        
        # Get authentication token
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack")
            return jsonify({'error': 'Failed to authenticate with BioTrack'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Fetch rooms from BioTrack
        logger.debug("Calling BioTrack API to fetch rooms")
        rooms_data = get_room_info(token)
        
        if rooms_data is None:
            logger.error("BioTrack API returned None - no rooms data")
            return jsonify({'error': 'Failed to fetch rooms from BioTrack'}), 500
        
        # Update local database with fresh data
        for room_id, room_info in rooms_data.items():
            # Convert room_id to string to match database schema
            room_id_str = str(room_id)
            existing_room = db.session.query(Room).filter_by(biotrack_room_id=room_id_str).first()
            if existing_room:
                existing_room.name = room_info['name']
                existing_room.is_active = room_info['is_active'] == 1
            else:
                new_room = Room(
                    biotrack_room_id=room_id_str,
                    name=room_info['name'],
                    is_active=room_info['is_active'] == 1
                )
                db.session.add(new_room)
        
        db.session.commit()
        
        # Log the refresh
        refresh_log = db.session.query(APIRefreshLog).filter_by(api_name='rooms').first()
        if refresh_log:
            refresh_log.last_refresh = datetime.now(UTC)
            refresh_log.records_count = len(rooms_data)
            refresh_log.status = 'success'
            refresh_log.error_message = None
        else:
            refresh_log = APIRefreshLog(
                api_name='rooms',
                records_count=len(rooms_data),
                status='success'
            )
            db.session.add(refresh_log)
        
        db.session.commit()
        
        # Convert to array format for response
        rooms_array = []
        for room_id, room_info in rooms_data.items():
            rooms_array.append({
                'id': str(room_id),  # Convert to string for consistency
                'name': room_info['name'],
                'is_active': room_info['is_active']
            })
        
        logger.info(f"Successfully refreshed and cached {len(rooms_array)} rooms from BioTrack")
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(rooms_array)} rooms',
            'rooms': rooms_array
        })
        
    except Exception as e:
        logger.error(f"Exception in refresh_rooms: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to refresh rooms from BioTrack'}), 500

@app.route('/api/vendors')
@login_required
def get_vendors():
    """API endpoint to get vendors from BioTrack (cached only)"""
    try:
        from models import Vendor
        
        # Get vendors from local database only - no automatic API calls
        # Use is_(True) to handle both boolean and integer values
        vendors = db.session.query(Vendor).filter(Vendor.is_active.is_(True)).all()
        
        # Convert to array format
        vendors_array = []
        for vendor in vendors:
            vendors_array.append({
                'id': vendor.id,  # Use actual database ID for foreign key relationships
                'biotrack_vendor_id': vendor.biotrack_vendor_id,
                'name': vendor.name,
                'license_info': vendor.license_info,
                'is_active': vendor.is_active
            })
        
        return jsonify({'success': True, 'vendors': vendors_array})
        
    except Exception as e:
        return jsonify({'error': f'Error fetching vendors: {str(e)}'}), 500

@app.route('/api/vendors/refresh', methods=['POST'])
@login_required
def refresh_vendors():
    """API endpoint to refresh vendors from BioTrack"""
    try:
        from api.biotrack import get_auth_token, get_vendor_info
        from models import Vendor, APIRefreshLog
        
        logger = logging.getLogger('app.refresh_vendors')
        logger.info("Starting vendors refresh from BioTrack")
        
        # Get authentication token
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack")
            return jsonify({'error': 'Failed to authenticate with BioTrack'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Fetch vendors from BioTrack
        logger.debug("Calling BioTrack API to fetch vendors")
        vendors_data = get_vendor_info(token)
        
        if vendors_data is None:
            logger.error("BioTrack API returned None - no vendors data")
            return jsonify({'error': 'Failed to fetch vendors from BioTrack'}), 500
        
        # Update local database with fresh data
        for vendor_location, vendor_info in vendors_data.items():
            existing_vendor = db.session.query(Vendor).filter_by(biotrack_vendor_id=vendor_location).first()
            if existing_vendor:
                existing_vendor.name = vendor_info['name']
                existing_vendor.license_info = vendor_info.get('license', '')
                existing_vendor.ubi = vendor_info.get('ubi', '')  # Store UBI for manifest creation
                existing_vendor.is_active = True  # All vendors from API are active
            else:
                new_vendor = Vendor(
                    biotrack_vendor_id=vendor_location,
                    name=vendor_info['name'],
                    license_info=vendor_info.get('license', ''),
                    ubi=vendor_info.get('ubi', ''),  # Store UBI for manifest creation
                    is_active=True  # All vendors from API are active
                )
                db.session.add(new_vendor)
        
        db.session.commit()
        
        # Log the refresh
        refresh_log = db.session.query(APIRefreshLog).filter_by(api_name='vendors').first()
        if refresh_log:
            refresh_log.last_refresh = datetime.now(UTC)
            refresh_log.records_count = len(vendors_data)
            refresh_log.status = 'success'
            refresh_log.error_message = None
        else:
            refresh_log = APIRefreshLog(
                api_name='vendors',
                records_count=len(vendors_data),
                status='success'
            )
            db.session.add(refresh_log)
        
        db.session.commit()
        
        # Convert to array format for response
        vendors_array = []
        for vendor_location, vendor_info in vendors_data.items():
            # Find the vendor in the database to get the actual ID
            vendor = db.session.query(Vendor).filter_by(biotrack_vendor_id=vendor_location).first()
            if vendor:
                vendors_array.append({
                    'id': vendor.id,  # Use actual database ID for foreign key relationships
                    'biotrack_vendor_id': vendor_location,
                    'name': vendor_info['name'],
                    'license_info': vendor_info.get('license', ''),
                    'ubi': vendor_info.get('ubi', ''),
                'is_active': True
            })
        
        logger.info(f"Successfully refreshed and cached {len(vendors_array)} vendors from BioTrack")
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(vendors_array)} vendors',
            'vendors': vendors_array
        })
        
    except Exception as e:
        logger.error(f"Exception in refresh_vendors: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to refresh vendors from BioTrack'}), 500

@app.route('/api/customers')
@login_required
def get_customers():
    """API endpoint to get customers from LeafTrade (cached only)"""
    try:
        from models import Customer
        
        # Get active customers from database cache
        customers = db.session.query(Customer).filter(Customer.is_active.is_(True)).all()
        
        # Convert to array format for response
        customers_array = []
        for customer in customers:
            customers_array.append({
                'id': customer.id,  # Database primary key for foreign key relationships
                'leaftrade_customer_id': customer.leaftrade_customer_id,  # LeafTrade ID for display
                'customer_name': customer.customer_name,
                'name': customer.name,
                'address': customer.address,
                'city': customer.city,
                'state': customer.state,
                'zip': customer.zip,
                'country': customer.country,
                'phone': customer.phone
            })
        
        return jsonify({'customers': customers_array})
        
    except Exception as e:
        return jsonify({'error': f'Error fetching customers: {str(e)}'}), 500

@app.route('/api/customers/refresh', methods=['POST'])
@login_required
def refresh_customers():
    """API endpoint to refresh customers from LeafTrade"""
    try:
        from api.leaftrade import get_customers
        from models import Customer, APIRefreshLog
        
        logger = logging.getLogger('app.refresh_customers')
        logger.info("Starting customers refresh from LeafTrade")
        
        # Fetch customers from LeafTrade
        logger.debug("Calling LeafTrade API to fetch customers")
        customers_data = get_customers()
        
        if customers_data is None:
            logger.error("LeafTrade API returned None - no customers data")
            return jsonify({'error': 'Failed to fetch customers from LeafTrade'}), 500
        
        # Update local database with fresh data
        for customer_info in customers_data:
            # Convert integer ID to string for database storage
            customer_id_str = str(customer_info['id'])
            existing_customer = db.session.query(Customer).filter_by(leaftrade_customer_id=customer_id_str).first()
            if existing_customer:
                existing_customer.customer_name = customer_info['customer_name']
                existing_customer.name = customer_info['name']
                existing_customer.address = customer_info.get('address', '')
                existing_customer.city = customer_info.get('city', '')
                existing_customer.state = customer_info.get('state', '')
                existing_customer.zip = customer_info.get('zip', '')
                existing_customer.country = customer_info.get('country', '')
                existing_customer.phone = customer_info.get('phone', '')
                existing_customer.is_active = True
            else:
                new_customer = Customer(
                    leaftrade_customer_id=customer_id_str,
                    customer_name=customer_info['customer_name'],
                    name=customer_info['name'],
                    address=customer_info.get('address', ''),
                    city=customer_info.get('city', ''),
                    state=customer_info.get('state', ''),
                    zip=customer_info.get('zip', ''),
                    country=customer_info.get('country', ''),
                    phone=customer_info.get('phone', ''),
                    is_active=True
                )
                db.session.add(new_customer)
        
        db.session.commit()
        
        # Log the refresh
        refresh_log = db.session.query(APIRefreshLog).filter_by(api_name='customers').first()
        if refresh_log:
            refresh_log.last_refresh = datetime.now(UTC)
            refresh_log.records_count = len(customers_data)
            refresh_log.status = 'success'
            refresh_log.error_message = None
        else:
            refresh_log = APIRefreshLog(
                api_name='customers',
                records_count=len(customers_data),
                status='success'
            )
            db.session.add(refresh_log)
        
        db.session.commit()
        
        logger.info(f"Successfully refreshed and cached {len(customers_data)} customers from LeafTrade")
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(customers_data)} customers',
            'customers': customers_data
        })
        
    except Exception as e:
        logger.error(f"Exception in refresh_customers: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to refresh customers from LeafTrade'}), 500

# Location Mapping API Endpoints
@app.route('/mapping')
@login_required
def mapping():
    """Location mapping interface page"""
    return render_template('mapping.html')

@app.route('/api/mapping')
@login_required
def get_mappings():
    """Get all location mappings"""
    try:
        mappings = db.session.query(LocationMapping).all()
        mappings_data = []
        
        for mapping in mappings:
            mappings_data.append({
                'id': mapping.id,
                'customer_id': mapping.customer_id,
                'biotrack_vendor_id': mapping.biotrack_vendor_id,
                'default_biotrack_room_id': mapping.default_biotrack_room_id,
                'is_active': mapping.is_active,
                'created_at': mapping.created_at.isoformat() if mapping.created_at else None,
                'updated_at': mapping.updated_at.isoformat() if mapping.updated_at else None
            })
        
        return jsonify(mappings_data)
        
    except Exception as e:
        logger = logging.getLogger('app.get_mappings')
        logger.error(f"Error fetching mappings: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error fetching mappings: {str(e)}'}), 500

@app.route('/api/mapping', methods=['POST'])
@login_required
def create_mapping():
    """Create a new location mapping"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('customer_id') or not data.get('biotrack_vendor_id'):
            return jsonify({'error': 'Customer ID and BioTrack Vendor ID are required'}), 400
        
        # Get customer to access leaftrade_customer_id
        customer = db.session.query(Customer).get(data['customer_id'])
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        # Use customer's leaftrade_customer_id as dispensary location ID
        leaftrade_dispensary_location_id = int(customer.leaftrade_customer_id)
        
        # Check if mapping already exists
        existing_mapping = db.session.query(LocationMapping).filter_by(
            leaftrade_dispensary_location_id=leaftrade_dispensary_location_id,
            biotrack_vendor_id=data['biotrack_vendor_id']
        ).first()
        
        if existing_mapping:
            return jsonify({'error': 'Mapping already exists for this customer and vendor'}), 409
        
        # Create new mapping
        new_mapping = LocationMapping(
            customer_id=data['customer_id'],
            leaftrade_dispensary_location_id=leaftrade_dispensary_location_id,
            biotrack_vendor_id=data['biotrack_vendor_id'],
            default_biotrack_room_id=data.get('default_biotrack_room_id'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(new_mapping)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Mapping created successfully',
            'mapping': {
                'id': new_mapping.id,
                'customer_id': new_mapping.customer_id,
                'leaftrade_dispensary_location_id': new_mapping.leaftrade_dispensary_location_id,
                'biotrack_vendor_id': new_mapping.biotrack_vendor_id,
                'default_biotrack_room_id': new_mapping.default_biotrack_room_id,
                'is_active': new_mapping.is_active
            }
        })
        
    except Exception as e:
        logger = logging.getLogger('app.create_mapping')
        logger.error(f"Error creating mapping: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Error creating mapping: {str(e)}'}), 500

@app.route('/api/mapping/<int:mapping_id>', methods=['PUT'])
@login_required
def update_mapping(mapping_id):
    """Update an existing location mapping"""
    try:
        mapping = db.session.query(LocationMapping).get(mapping_id)
        if not mapping:
            return jsonify({'error': 'Mapping not found'}), 404
        
        data = request.get_json()
        
        # Update fields
        if 'customer_id' in data:
            # Get customer to access leaftrade_customer_id
            customer = db.session.query(Customer).get(data['customer_id'])
            if not customer:
                return jsonify({'error': 'Customer not found'}), 404
            
            mapping.customer_id = data['customer_id']
            # Update dispensary location ID when customer changes
            mapping.leaftrade_dispensary_location_id = int(customer.leaftrade_customer_id)
            
        if 'biotrack_vendor_id' in data:
            mapping.biotrack_vendor_id = data['biotrack_vendor_id']
        if 'default_biotrack_room_id' in data:
            mapping.default_biotrack_room_id = data['default_biotrack_room_id']
        if 'is_active' in data:
            mapping.is_active = data['is_active']
        
        mapping.updated_at = get_est_now()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Mapping updated successfully',
            'mapping': {
                'id': mapping.id,
                'customer_id': mapping.customer_id,
                'leaftrade_dispensary_location_id': mapping.leaftrade_dispensary_location_id,
                'biotrack_vendor_id': mapping.biotrack_vendor_id,
                'default_biotrack_room_id': mapping.default_biotrack_room_id,
                'is_active': mapping.is_active
            }
        })
        
    except Exception as e:
        logger = logging.getLogger('app.update_mapping')
        logger.error(f"Error updating mapping: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Error updating mapping: {str(e)}'}), 500

@app.route('/api/mapping/<int:mapping_id>', methods=['DELETE'])
@login_required
def delete_mapping(mapping_id):
    """Delete a location mapping"""
    try:
        mapping = db.session.query(LocationMapping).get(mapping_id)
        if not mapping:
            return jsonify({'error': 'Mapping not found'}), 404
        
        db.session.delete(mapping)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Mapping deleted successfully'
        })
        
    except Exception as e:
        logger = logging.getLogger('app.delete_mapping')
        logger.error(f"Error deleting mapping: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Error deleting mapping: {str(e)}'}), 500

@app.route('/api/mapping/export')
@login_required
def export_mappings():
    """Export mappings as CSV"""
    try:
        from io import StringIO
        import csv
        from models import Vendor
        
        # Join LocationMapping with Customer and Vendor tables
        mappings = db.session.query(LocationMapping, Customer, Vendor).join(
            Customer, LocationMapping.customer_id == Customer.id
        ).outerjoin(
            Vendor, LocationMapping.biotrack_vendor_id == Vendor.biotrack_vendor_id
        ).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Customer Name', 'Customer Location', 'BioTrack Vendor ID', 'Vendor Name', 'Default Room', 'Status'])
        
        # Write data
        for mapping, customer, vendor in mappings:
            writer.writerow([
                customer.customer_name,
                customer.name,
                mapping.biotrack_vendor_id,
                vendor.name if vendor else 'Unknown Vendor',
                mapping.default_biotrack_room_id or '',
                'Active' if mapping.is_active else 'Inactive'
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=mappings.csv'}
        )
        
    except Exception as e:
        logger = logging.getLogger('app.export_mappings')
        logger.error(f"Error exporting mappings: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error exporting mappings: {str(e)}'}), 500

@app.route('/api/contacts/export')
@login_required
def export_contacts():
    """Export customer contacts as CSV"""
    try:
        from io import StringIO
        import csv
        
        contacts = db.session.query(CustomerContact).join(Vendor).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Contact Name', 'Email', 'Vendor Name', 'Is Primary', 'Email Invoice', 'Email Manifest'])
        
        # Write data
        for contact in contacts:
            writer.writerow([
                contact.contact_name,
                contact.email,
                contact.vendor.name if contact.vendor else '',
                'Yes' if contact.is_primary else 'No',
                'Yes' if contact.email_invoice else 'No',
                'Yes' if contact.email_manifest else 'No'
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=contacts.csv'}
        )
        
    except Exception as e:
        logger = logging.getLogger('app.export_contacts')
        logger.error(f"Error exporting contacts: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error exporting contacts: {str(e)}'}), 500

@app.route('/api/vendors/export')
@login_required
def export_vendors():
    """Export vendors as CSV"""
    try:
        from io import StringIO
        import csv
        
        vendors = db.session.query(Vendor).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Name', 'License', 'UBI', 'Is Active', 'Created At'])
        
        # Write data
        for vendor in vendors:
            writer.writerow([
                vendor.name,
                vendor.license_info or '',
                vendor.ubi or '',
                'Yes' if vendor.is_active else 'No',
                vendor.created_at.strftime('%Y-%m-%d %H:%M:%S') if vendor.created_at else ''
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=vendors.csv'}
        )
        
    except Exception as e:
        logger = logging.getLogger('app.export_vendors')
        logger.error(f"Error exporting vendors: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error exporting vendors: {str(e)}'}), 500

@app.route('/api/customers/export')
@login_required
def export_customers():
    """Export customers as CSV"""
    try:
        from io import StringIO
        import csv
        
        customers = db.session.query(Customer).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Customer Name', 'Location Name', 'Address', 'City', 'State', 'Zip', 'Phone', 'Is Active', 'Created At'])
        
        # Write data
        for customer in customers:
            writer.writerow([
                customer.customer_name,
                customer.name,
                customer.address or '',
                customer.city or '',
                customer.state or '',
                customer.zip or '',
                customer.phone or '',
                'Yes' if customer.is_active else 'No',
                customer.created_at.strftime('%Y-%m-%d %H:%M:%S') if customer.created_at else ''
            ])
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=customers.csv'}
        )
        
    except Exception as e:
        logger = logging.getLogger('app.export_customers')
        logger.error(f"Error exporting customers: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error exporting customers: {str(e)}'}), 500

@app.route('/api/biotrack/refresh', methods=['POST'])
@login_required
def refresh_biotrack_data():
    """Refresh all BioTrack data using current training mode"""
    try:
        logger = logging.getLogger('app.refresh_biotrack_data')
        logger.info(f"Starting BioTrack data refresh in training mode: {get_training_mode()}")
        
        # Clear existing BioTrack data
        db.session.query(Driver).delete()
        db.session.query(Vehicle).delete()
        db.session.query(Vendor).delete()
        db.session.query(Room).delete()
        db.session.commit()
        logger.info("Cleared existing BioTrack data")
        
        # Refresh drivers
        try:
            from api.biotrack import get_driver_info
            drivers_data = get_driver_info()
            if drivers_data:
                for driver in drivers_data:
                    new_driver = Driver(
                        biotrack_id=driver['id'],
                        name=driver['name'],
                        license_number=driver.get('license_number', ''),
                        is_active=driver.get('is_active', True)
                    )
                    db.session.add(new_driver)
                logger.info(f"Added {len(drivers_data)} drivers")
        except Exception as e:
            logger.error(f"Error refreshing drivers: {str(e)}")
            return jsonify({'error': f'Error refreshing drivers: {str(e)}'}), 500
        
        # Refresh vehicles
        try:
            from api.biotrack import get_vehicle_info
            vehicles_data = get_vehicle_info()
            if vehicles_data:
                for vehicle in vehicles_data:
                    new_vehicle = Vehicle(
                        biotrack_id=vehicle['id'],
                        name=vehicle['name'],
                        license_plate=vehicle.get('license_plate', ''),
                        is_active=vehicle.get('is_active', True)
                    )
                    db.session.add(new_vehicle)
                logger.info(f"Added {len(vehicles_data)} vehicles")
        except Exception as e:
            logger.error(f"Error refreshing vehicles: {str(e)}")
            return jsonify({'error': f'Error refreshing vehicles: {str(e)}'}), 500
        
        # Refresh vendors
        try:
            from api.biotrack import get_vendor_info
            vendors_data = get_vendor_info()
            if vendors_data:
                for vendor_location, vendor_info in vendors_data.items():
                    new_vendor = Vendor(
                        biotrack_vendor_id=vendor_location,
                        name=vendor_info['name'],
                        license_info=vendor_info.get('license', ''),
                        ubi=vendor_info.get('ubi', ''),
                        is_active=True
                    )
                    db.session.add(new_vendor)
                logger.info(f"Added {len(vendors_data)} vendors")
        except Exception as e:
            logger.error(f"Error refreshing vendors: {str(e)}")
            return jsonify({'error': f'Error refreshing vendors: {str(e)}'}), 500
        
        # Refresh rooms
        try:
            from api.biotrack import get_room_info
            rooms_data = get_room_info()
            if rooms_data:
                for room in rooms_data:
                    new_room = Room(
                        biotrack_id=room['id'],
                        name=room['name'],
                        vendor_id=room.get('vendor_id'),
                        is_active=room.get('is_active', True)
                    )
                    db.session.add(new_room)
                logger.info(f"Added {len(rooms_data)} rooms")
        except Exception as e:
            logger.error(f"Error refreshing rooms: {str(e)}")
            return jsonify({'error': f'Error refreshing rooms: {str(e)}'}), 500
        
        # Commit all changes
        db.session.commit()
        
        logger.info("BioTrack data refresh completed successfully")
        return jsonify({
            'success': True,
            'message': f'BioTrack data refreshed successfully in {"training" if is_training_mode() else "production"} mode'
        })
        
    except Exception as e:
        logger = logging.getLogger('app.refresh_biotrack_data')
        logger.error(f"Error during BioTrack data refresh: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'Error refreshing BioTrack data: {str(e)}'}), 500

def process_order_sublots(leaftrade_order_id: str, target_room_id: str = None) -> dict:
    """
    Process a single LeafTrade order for sublot creation and movement.
    
    Args:
        leaftrade_order_id: LeafTrade order ID to process
        target_room_id: Optional BioTrack room ID override (uses mapping default if None)
    
    Returns:
        dict: {
            'success': bool,
            'order_id': str,
            'sublots_created': list,  # New barcode IDs
            'room_moved_to': str,
            'error': str (if failed)
        }
    """
    logger = logging.getLogger('app.process_order_sublots')
    
    try:
        # Initialize BioTrack API
        from api.biotrack import get_auth_token, post_sublot, post_sublot_move
        from api.leaftrade import get_order_details
        
        # Authenticate with BioTrack
        token = get_auth_token()
        if not token:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'Failed to authenticate with BioTrack API'
            }
        
        # Get order details from LeafTrade
        order_details = get_order_details(leaftrade_order_id)
        if not order_details:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'Failed to get order details from LeafTrade'
            }
        
        # Extract dispensary location ID
        dispensary_location_id = order_details.get('order', {}).get('dispensary_location', {}).get('id')
        if not dispensary_location_id:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'No dispensary location ID found in order details'
            }
        
        # Find location mapping
        location_mapping = db.session.query(LocationMapping).filter_by(
            leaftrade_dispensary_location_id=dispensary_location_id
        ).first()
        
        if not location_mapping:
            # Get dispensary name for better error messages
            dispensary_location = order_details.get('order', {}).get('dispensary_location', {})
            dispensary_name = dispensary_location.get('name', 'Unknown Dispensary')
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': f'No location mapping found for "{dispensary_name}" (ID: {dispensary_location_id})'
            }
        
        # Determine target room
        room_id = target_room_id or location_mapping.default_biotrack_room_id or 'default_room'
        
        # Process line items for sublot creation
        line_items = order_details.get('line_items', [])
        sublot_data = []
        
        for line_item in line_items:
            barcode_id = line_item.get('barcode_id')
            quantity = line_item.get('quantity', 1)
            if barcode_id:
                sublot_data.append({
                    'barcodeid': barcode_id,
                    'remove_quantity': str(quantity)
                })
        
        if not sublot_data:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'No barcode IDs found in line items'
            }
        
        # Create sublots
        new_barcode_ids = post_sublot(token, "bulk_create", sublot_data)
        if new_barcode_ids is None:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'Failed to create sublots'
            }
        
        if not new_barcode_ids:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'No barcode IDs returned from sublot creation'
            }
        
        # Move sublots to room
        move_data = []
        for barcode_id in new_barcode_ids:
            move_data.append({
                'barcodeid': barcode_id,
                'room': room_id
            })
        
        move_result = post_sublot_move(token, move_data)
        if not move_result:
            return {
                'success': False,
                'order_id': leaftrade_order_id,
                'error': 'Failed to move sublots to room'
            }
        
        # Success
        return {
            'success': True,
            'order_id': leaftrade_order_id,
            'sublots_created': new_barcode_ids,
            'room_moved_to': room_id,
            'line_items_processed': len(sublot_data),
            'customer_name': order_details.get('order', {}).get('dispensary_location', {}).get('dispensary', {}).get('name', 'Unknown')
        }
        
    except Exception as e:
        logger.error(f"Error processing order {leaftrade_order_id}: {str(e)}")
        return {
            'success': False,
            'order_id': leaftrade_order_id,
            'error': f'Unexpected error: {str(e)}'
        }


@app.route('/api/orders/<order_id>/process-sublots', methods=['POST'])
@login_required
def process_order_sublots_endpoint(order_id):
    """Process a single order for sublot creation and movement"""
    logger = logging.getLogger('app.process_order_sublots_endpoint')
    
    try:
        # Get optional room override from request
        target_room = None
        if request.is_json:
            target_room = request.json.get('target_room_id')
        
        logger.info(f"Processing sublots for order {order_id} with room override: {target_room}")
        
        # Call the standalone function
        result = process_order_sublots(order_id, target_room)
        
        if result['success']:
            logger.info(f"Successfully processed order {order_id}: created {len(result['sublots_created'])} sublots")
            return jsonify(result), 200
        else:
            logger.error(f"Failed to process order {order_id}: {result['error']}")
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Unexpected error in process_order_sublots_endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'order_id': order_id,
            'error': f'Endpoint error: {str(e)}'
        }), 500

@app.route('/order-processing')
@login_required
def order_processing():
    """Order processing page for single order sublot processing"""
    return render_template('order_processing.html')

def _is_valid_biotrack_uid(barcode_id):
    """Validate that barcode_id is a standard BioTrack UID (16-digit number)"""
    if not barcode_id:
        return False
    
    # Convert to string and check if it's exactly 16 digits
    barcode_str = str(barcode_id).strip()
    return len(barcode_str) == 16 and barcode_str.isdigit()

def validate_trip(trip_id):
    """Validate trip using existing logic patterns from execute_trip"""
    logger = logging.getLogger('app.validate_trip')
    
    try:
        trip = Trip.query.get_or_404(trip_id)
        
        if trip.status == 'completed':
            return {
                'valid': False,
                'errors': ['Trip is not in pending or validated status'],
                'summary': 'Trip cannot be validated - not in pending status'
            }
        
        # Get trip orders with sequence
        trip_orders = db.session.query(TripOrder).filter_by(trip_id=trip_id).order_by(TripOrder.sequence_order).all()
        
        if not trip_orders:
            return {
                'valid': False,
                'errors': ['No orders found for trip'],
                'summary': 'Trip cannot be validated - no orders found'
            }
        
        # Get driver and vehicle information
        driver1 = db.session.get(Driver, trip.driver1_id)
        driver2 = db.session.get(Driver, trip.driver2_id)
        vehicle = db.session.get(Vehicle, trip.vehicle_id)
        
        if not driver1 or not driver2 or not vehicle:
            return {
                'valid': False,
                'errors': ['Driver or vehicle information not found'],
                'summary': 'Trip cannot be validated - missing driver or vehicle information'
            }
        
        # Initialize BioTrack API for authentication check
        from api.biotrack import get_auth_token
        from api.leaftrade import get_order_details
        
        # Check BioTrack authentication
        try:
            token = get_auth_token()
            if not token:
                return {
                    'valid': False,
                    'errors': ['Failed to authenticate with BioTrack API'],
                    'summary': 'Trip cannot be validated - BioTrack authentication failed'
                }
        except Exception as e:
            logger.error(f"BioTrack authentication error: {str(e)}")
            return {
                'valid': False,
                'errors': [f'BioTrack authentication failed: {str(e)}'],
                'summary': 'Trip cannot be validated - BioTrack authentication error'
            }
        
        # Validate each order and aggregate inventory requirements
        validation_errors = []
        validation_summary = []
        inventory_requirements = {}  # barcode_id -> total_quantity_needed
        
        for trip_order in trip_orders:
            order_errors = []
            
            # Get order details from LeafTrade
            try:
                order_details = get_order_details(trip_order.order_id)
                if not order_details:
                    order_errors.append(f'Failed to get order details for {trip_order.order_id}')
                else:
                    validation_summary.append(f'✓ Order {trip_order.order_id}: LeafTrade data retrieved')
            except Exception as e:
                order_errors.append(f'Error getting order details for {trip_order.order_id}: {str(e)}')
                continue
            
            if order_errors:
                validation_errors.extend(order_errors)
                continue
            
            # Check location mapping
            dispensary_location_id = order_details.get('order', {}).get('dispensary_location', {}).get('id')
            if not dispensary_location_id:
                order_errors.append(f'No dispensary location ID found in order details for {trip_order.order_id}')
            else:
                # Get dispensary name for better error messages
                dispensary_location = order_details.get('order', {}).get('dispensary_location', {})
                dispensary_name = dispensary_location.get('name', 'Unknown Dispensary')
                
                location_mapping = db.session.query(LocationMapping).filter_by(
                    leaftrade_dispensary_location_id=dispensary_location_id
                ).first()
                
                if not location_mapping:
                    order_errors.append(f'No location mapping found for "{dispensary_name}" (ID: {dispensary_location_id})')
                else:
                    validation_summary.append(f'✓ Order {trip_order.order_id}: Location mapping found for "{dispensary_name}"')
            
            # Check line items and barcode IDs, aggregate quantities
            line_items = order_details.get('line_items', [])
            barcode_ids = []
            invalid_uid_count = 0
            
            for line_item in line_items:
                barcode_id = line_item.get('barcode_id')
                quantity = line_item.get('quantity', 0)
                
                # Only process line items with valid BioTrack UIDs (16-digit numbers)
                if barcode_id and _is_valid_biotrack_uid(barcode_id):
                    barcode_ids.append(barcode_id)
                    
                    # Aggregate quantities by barcode_id
                    if barcode_id in inventory_requirements:
                        inventory_requirements[barcode_id] += quantity
                    else:
                        inventory_requirements[barcode_id] = quantity
                elif barcode_id:
                    invalid_uid_count += 1
                    logger.warning(f"Skipping invalid BioTrack UID in validation: {barcode_id} (not 16 digits)")
            
            # Log summary of filtered items
            if invalid_uid_count > 0:
                logger.info(f"Filtered out {invalid_uid_count} line items with invalid BioTrack UIDs during validation")
            
            if not barcode_ids:
                order_errors.append(f'No valid BioTrack UIDs (16-digit numbers) found for order {trip_order.order_id}')
            else:
                validation_summary.append(f'✓ Order {trip_order.order_id}: {len(barcode_ids)} valid BioTrack UIDs found')
            
            if order_errors:
                validation_errors.extend(order_errors)
        
        # Check inventory availability if we have requirements
        if inventory_requirements:
            try:
                from api.biotrack import get_inventory_info
                
                # Get current inventory from BioTrack
                inventory_data = get_inventory_info(token)
                
                if not inventory_data:
                    validation_errors.append('Failed to retrieve inventory data from BioTrack')
                else:
                    validation_summary.append(f'✓ BioTrack inventory data retrieved')
                    
                    # Check each required SKU against available inventory
                    for barcode_id, required_quantity in inventory_requirements.items():
                        if barcode_id in inventory_data:
                            available_quantity = inventory_data[barcode_id].get('quantity', 0)
                            
                            # Convert to float for comparison (in case quantities are strings)
                            try:
                                available_quantity = float(available_quantity)
                                required_quantity = float(required_quantity)
                                
                                if available_quantity < required_quantity:
                                    validation_errors.append(
                                        f'Insufficient inventory for SKU {barcode_id}: '
                                        f'required {required_quantity}, available {available_quantity}'
                                    )
                                else:
                                    validation_summary.append(
                                        f'✓ SKU {barcode_id}: {required_quantity} units available '
                                        f'(required: {required_quantity}, available: {available_quantity})'
                                    )
                            except (ValueError, TypeError) as e:
                                validation_errors.append(
                                    f'Invalid quantity format for SKU {barcode_id}: {str(e)}'
                                )
                        else:
                            validation_errors.append(f'SKU {barcode_id} not found in BioTrack inventory')
            except Exception as e:
                logger.error(f"Inventory check error: {str(e)}")
                validation_errors.append(f'Error checking inventory: {str(e)}')
        
        # Check if we have any validation errors
        if validation_errors:
            return {
                'valid': False,
                'errors': validation_errors,
                'summary': f'Trip validation failed with {len(validation_errors)} errors'
            }
        
        # All validations passed - update trip status to validated
        trip.status = 'validated'
        db.session.commit()
        
        return {
            'valid': True,
            'errors': [],
            'summary': f'Trip validation successful - {len(trip_orders)} orders validated'
        }
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error in validate_trip: {str(e)}")
        return {
            'valid': False,
            'errors': [f'Error validating trip: {str(e)}'],
            'summary': 'Trip validation failed due to unexpected error'
        }

@app.route('/api/trips/<int:trip_id>/validate', methods=['POST'])
@login_required
def validate_trip_endpoint(trip_id):
    """Validate trip before execution"""
    logger = logging.getLogger('app.validate_trip_endpoint')
    
    try:
        validation_result = validate_trip(trip_id)
        
        if validation_result['valid']:
            return jsonify({
                'success': True,
                'message': validation_result['summary'],
                'valid': True
            })
        else:
            return jsonify({
                'success': False,
                'error': validation_result['summary'],
                'errors': validation_result['errors'],
                'valid': False
            }), 400
            
    except Exception as e:
        logger.error(f"Error in validate_trip_endpoint: {str(e)}")
        return jsonify({'error': f'Error validating trip: {str(e)}'}), 500

# Email Delivery System API Endpoints

@app.route('/api/trip-orders/<int:trip_order_id>/documents', methods=['POST'])
@login_required
def upload_document(trip_order_id):
    """Upload manifest or invoice document"""
    try:
        from utils.document_service import DocumentService
        
        file = request.files['document']
        document_type = request.form['document_type']  # 'manifest' or 'invoice'
        
        if document_type not in ['manifest', 'invoice']:
            return jsonify({'error': 'Invalid document type'}), 400
        
        if not file or not file.filename:
            return jsonify({'error': 'No file provided'}), 400
        
        # Read file data
        file_data = file.read()
        
        # Store document
        document_service = DocumentService()
        success = document_service.store_document(
            trip_order_id, document_type, file_data
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Document uploaded successfully'})
        else:
            return jsonify({'error': 'Failed to upload document'}), 500
            
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/trip-orders/<int:trip_order_id>/send-email', methods=['POST'])
@login_required
def send_trip_order_email(trip_order_id):
    """Send email for specific trip order"""
    try:
        from utils.document_service import DocumentService
        from api.email_service import EmailService
        
        document_service = DocumentService()
        email_service = EmailService()
        
        result = email_service.send_trip_order_email(trip_order_id, document_service)
        
        # Check if there was an error
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        # Create user-friendly message
        messages = []
        if result['invoice_sent']:
            messages.append(f"Invoice email sent to {result['invoice_contacts']} contact(s)")
        elif result['invoice_contacts'] == 0:
            messages.append("No invoice contacts configured")
        
        if result['manifest_sent']:
            messages.append(f"Manifest email sent to {result['manifest_contacts']} contact(s)")
        elif result['manifest_contacts'] == 0:
            messages.append("No manifest contacts configured")
        
        if not result['invoice_sent'] and not result['manifest_sent']:
            return jsonify({'error': 'No emails sent - no contacts configured for this vendor'}), 400
        
        return jsonify({
            'success': True, 
            'message': '; '.join(messages),
            'details': result
        })
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/trips/<int:trip_id>/send-bulk-emails', methods=['POST'])
@login_required
def send_bulk_trip_emails(trip_id):
    """Send emails for all ready trip orders in trip"""
    try:
        from utils.document_service import DocumentService
        from api.email_service import EmailService
        from models import TripOrder
        
        document_service = DocumentService()
        email_service = EmailService()
        
        ready_orders = TripOrder.query.filter_by(
            trip_id=trip_id, email_ready=True
        ).all()
        
        results = []
        total_invoice_sent = 0
        total_manifest_sent = 0
        total_invoice_contacts = 0
        total_manifest_contacts = 0
        
        for order in ready_orders:
            result = email_service.send_trip_order_email(order.id, document_service)
            results.append({
                'order_id': order.order_id,
                'invoice_sent': result.get('invoice_sent', False),
                'manifest_sent': result.get('manifest_sent', False),
                'invoice_contacts': result.get('invoice_contacts', 0),
                'manifest_contacts': result.get('manifest_contacts', 0),
                'error': result.get('error')
            })
            
            # Aggregate totals
            if result.get('invoice_sent'):
                total_invoice_sent += 1
            if result.get('manifest_sent'):
                total_manifest_sent += 1
            total_invoice_contacts += result.get('invoice_contacts', 0)
            total_manifest_contacts += result.get('manifest_contacts', 0)
        
        # Create summary message
        summary_messages = []
        if total_invoice_sent > 0:
            summary_messages.append(f"{total_invoice_sent} invoice email(s) sent to {total_invoice_contacts} total contact(s)")
        if total_manifest_sent > 0:
            summary_messages.append(f"{total_manifest_sent} manifest email(s) sent to {total_manifest_contacts} total contact(s)")
        
        return jsonify({
            'success': True, 
            'results': results,
            'summary': {
                'total_orders': len(results),
                'invoice_emails_sent': total_invoice_sent,
                'manifest_emails_sent': total_manifest_sent,
                'total_invoice_contacts': total_invoice_contacts,
                'total_manifest_contacts': total_manifest_contacts
            },
            'message': f'Processed {len(results)} orders. ' + '; '.join(summary_messages) if summary_messages else 'No emails sent'
        })
    except Exception as e:
        logger.error(f"Error sending bulk emails: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/trip-orders/<int:trip_order_id>/documents/<document_type>', methods=['DELETE'])
@login_required
def delete_document(trip_order_id, document_type):
    """Delete a document from trip order"""
    try:
        from utils.document_service import DocumentService
        
        if document_type not in ['manifest', 'invoice']:
            return jsonify({'error': 'Invalid document type'}), 400
        
        document_service = DocumentService()
        success = document_service.delete_document(trip_order_id, document_type)
        
        if success:
            return jsonify({'success': True, 'message': 'Document deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete document'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        return jsonify({'error': str(e)}), 500

# Customer Contact Management API Endpoints

@app.route('/api/contacts')
@login_required
def get_contacts():
    """Get all customer contacts"""
    try:
        from models import CustomerContact, Vendor
        
        contacts = CustomerContact.query.join(Vendor).all()
        contacts_data = []
        
        for contact in contacts:
            contacts_data.append({
                'id': contact.id,
                'vendor_id': contact.vendor_id,
                'vendor_name': contact.vendor.name,
                'contact_name': contact.contact_name,
                'email': contact.email,
                'is_primary': contact.is_primary,
                'email_invoice': contact.email_invoice,
                'email_manifest': contact.email_manifest
            })
        
        return jsonify({'success': True, 'contacts': contacts_data})
        
    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/contacts', methods=['POST'])
@login_required
def create_contact():
    """Create a new customer contact"""
    try:
        from models import CustomerContact
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['vendor_id', 'contact_name', 'email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Create new contact
        contact = CustomerContact(
            vendor_id=data['vendor_id'],
            contact_name=data['contact_name'],
            email=data['email'],
            is_primary=data.get('is_primary', False),
            email_invoice=data.get('email_invoice', True),
            email_manifest=data.get('email_manifest', True)
        )
        
        db.session.add(contact)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Contact created successfully',
            'contact_id': contact.id
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating contact: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/contacts/<int:contact_id>', methods=['PUT'])
@login_required
def update_contact(contact_id):
    """Update a customer contact"""
    try:
        from models import CustomerContact
        
        contact = CustomerContact.query.get(contact_id)
        if not contact:
            return jsonify({'error': 'Contact not found'}), 404
        
        data = request.get_json()
        
        # Update fields
        if 'contact_name' in data:
            contact.contact_name = data['contact_name']
        if 'email' in data:
            contact.email = data['email']
        if 'is_primary' in data:
            contact.is_primary = data['is_primary']
        if 'email_invoice' in data:
            contact.email_invoice = data['email_invoice']
        if 'email_manifest' in data:
            contact.email_manifest = data['email_manifest']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Contact updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating contact: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_contact(contact_id):
    """Delete a customer contact"""
    try:
        from models import CustomerContact
        
        contact = CustomerContact.query.get(contact_id)
        if not contact:
            return jsonify({'error': 'Contact not found'}), 404
        
        db.session.delete(contact)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Contact deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting contact: {e}")
        return jsonify({'error': str(e)}), 500

# Internal Contacts API endpoints
@app.route('/api/internal-contacts')
@login_required
def get_internal_contacts():
    """Get all internal contacts"""
    try:
        contacts = InternalContact.query.order_by(InternalContact.name).all()
        return jsonify([{
            'id': contact.id,
            'name': contact.name,
            'email': contact.email,
            'is_active': contact.is_active,
            'created_at': contact.created_at.isoformat() if contact.created_at else None
        } for contact in contacts])
    except Exception as e:
        logger.error(f"Error getting internal contacts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/internal-contacts', methods=['POST'])
@login_required
def create_internal_contact():
    """Create a new internal contact"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name') or not data.get('email'):
            return jsonify({'error': 'Name and email are required'}), 400
        
        # Check if email already exists
        existing_contact = InternalContact.query.filter_by(email=data['email']).first()
        if existing_contact:
            return jsonify({'error': 'Email already exists'}), 400
        
        contact = InternalContact(
            name=data['name'],
            email=data['email'],
            is_active=data.get('is_active', True)
        )
        
        db.session.add(contact)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Internal contact created successfully',
            'contact': {
                'id': contact.id,
                'name': contact.name,
                'email': contact.email,
                'is_active': contact.is_active,
                'created_at': contact.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating internal contact: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/internal-contacts/<int:contact_id>', methods=['PUT'])
@login_required
def update_internal_contact(contact_id):
    """Update an internal contact"""
    try:
        contact = InternalContact.query.get(contact_id)
        if not contact:
            return jsonify({'error': 'Internal contact not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Check if email already exists (excluding current contact)
        if 'email' in data and data['email'] != contact.email:
            existing_contact = InternalContact.query.filter_by(email=data['email']).first()
            if existing_contact:
                return jsonify({'error': 'Email already exists'}), 400
        
        # Update fields
        if 'name' in data:
            contact.name = data['name']
        if 'email' in data:
            contact.email = data['email']
        if 'is_active' in data:
            contact.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Internal contact updated successfully',
            'contact': {
                'id': contact.id,
                'name': contact.name,
                'email': contact.email,
                'is_active': contact.is_active,
                'created_at': contact.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating internal contact: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/internal-contacts/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_internal_contact(contact_id):
    """Delete an internal contact"""
    try:
        contact = InternalContact.query.get(contact_id)
        if not contact:
            return jsonify({'error': 'Internal contact not found'}), 404
        
        db.session.delete(contact)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Internal contact deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting internal contact: {e}")
        return jsonify({'error': str(e)}), 500

# Global Preferences API endpoints
@app.route('/api/global-preferences')
@login_required
def get_global_preferences():
    """Get all global preferences"""
    try:
        preferences = GlobalPreference.query.all()
        preferences_dict = {pref.preference_key: pref.preference_value for pref in preferences}
        return jsonify({'success': True, 'preferences': preferences_dict})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences/<preference_key>')
@login_required
def get_global_preference(preference_key):
    """Get specific global preference"""
    try:
        preference = GlobalPreference.query.filter_by(preference_key=preference_key).first()
        if not preference:
            return jsonify({'error': 'Preference not found'}), 404
        return jsonify({'success': True, 'preference_key': preference.preference_key, 'preference_value': preference.preference_value})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences', methods=['POST'])
@login_required
def create_global_preference():
    """Create new global preference"""
    try:
        data = request.get_json()
        preference_key = data.get('preference_key')
        preference_value = data.get('preference_value')
        
        if not preference_key or preference_value is None:
            return jsonify({'error': 'preference_key and preference_value are required'}), 400
        
        # Check if preference already exists
        existing = GlobalPreference.query.filter_by(preference_key=preference_key).first()
        if existing:
            return jsonify({'error': 'Preference already exists'}), 400
        
        preference = GlobalPreference(
            preference_key=preference_key,
            preference_value=preference_value
        )
        db.session.add(preference)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Preference created successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences/<preference_key>', methods=['PUT'])
@login_required
def update_global_preference(preference_key):
    """Update existing global preference"""
    try:
        data = request.get_json()
        preference_value = data.get('preference_value')
        
        if preference_value is None:
            return jsonify({'error': 'preference_value is required'}), 400
        
        preference = GlobalPreference.query.filter_by(preference_key=preference_key).first()
        if not preference:
            return jsonify({'error': 'Preference not found'}), 404
        
        preference.preference_value = preference_value
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Preference updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences/<preference_key>', methods=['DELETE'])
@login_required
def delete_global_preference(preference_key):
    """Delete global preference"""
    try:
        preference = GlobalPreference.query.filter_by(preference_key=preference_key).first()
        if not preference:
            return jsonify({'error': 'Preference not found'}), 404
        
        db.session.delete(preference)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Preference deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Room Selection Management API endpoints
@app.route('/api/global-preferences/rooms')
@login_required
def get_selected_rooms():
    """Get selected rooms for finished goods report"""
    try:
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if not preference:
            return jsonify({'success': True, 'selected_rooms': []})
        
        # Parse comma-separated room IDs
        selected_rooms = [room_id.strip() for room_id in preference.preference_value.split(',') if room_id.strip()]
        return jsonify({'success': True, 'selected_rooms': selected_rooms})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences/rooms', methods=['POST'])
@login_required
def save_selected_rooms():
    """Save selected rooms for finished goods report"""
    try:
        data = request.get_json()
        selected_rooms = data.get('selected_rooms', [])
        
        if not isinstance(selected_rooms, list):
            return jsonify({'error': 'selected_rooms must be a list'}), 400
        
        # Convert to comma-separated string
        rooms_string = ','.join(str(room_id) for room_id in selected_rooms)
        
        # Update or create preference
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if preference:
            preference.preference_value = rooms_string
        else:
            preference = GlobalPreference(
                preference_key='finished_goods_rooms',
                preference_value=rooms_string
            )
            db.session.add(preference)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Room selections saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-preferences/rooms', methods=['DELETE'])
@login_required
def clear_selected_rooms():
    """Clear selected rooms for finished goods report"""
    try:
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if preference:
            db.session.delete(preference)
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Room selections cleared successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/contacts')
@login_required
def contacts():
    """Customer contacts management page"""
    return render_template('contacts.html')

@app.route('/api/inventory-report')
@login_required
def get_inventory_report():
    """Get comprehensive inventory report with lab data and room information"""
    logger = logging.getLogger('app.inventory_report')
    logger.info("Generating inventory report with lab data")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
        
        # Authenticate with BioTrack
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Get inventory data
        logger.debug("Calling BioTrack API to fetch inventory")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            logger.error("Failed to retrieve inventory data from BioTrack")
            return jsonify({'error': 'Failed to retrieve inventory data'}), 500
        
        # Log inventory data structure for debugging
        logger.debug(f"Retrieved {len(inventory_data)} inventory items")
        for item_id, item_info in list(inventory_data.items())[:3]:  # Log first 3 items
            logger.debug(f"Inventory item {item_id}: {item_info}")
        
        # Get room data for room name lookup
        logger.debug("Calling BioTrack API to fetch rooms")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Process inventory items
        inventory_items = []
        items_with_lab_data = 0
        items_without_lab_data = 0
        
        for item_id, item_info in inventory_data.items():
            try:
                # Get room name - use correct field name from BioTrack response
                current_room_id = str(item_info.get('currentroom', ''))
                current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
                
                # Try to get lab data for this item (ensure barcode_id is string)
                # Check if this inventory item has a barcode_id we can use for QA check
                barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
                lab_results = None
                
                if barcode_id:
                    try:
                        logger.debug(f"Attempting QA check for barcode: {barcode_id}")
                        lab_results = get_inventory_qa_check(token, barcode_id)
                        if lab_results:
                            logger.debug(f"Found lab data for barcode {barcode_id}: {lab_results}")
                        else:
                            logger.debug(f"No lab data found for barcode {barcode_id}")
                    except Exception as e:
                        logger.warning(f"Error getting lab data for barcode {barcode_id}: {str(e)}")
                        lab_results = None
                
                # Create inventory item entry - use correct field names from BioTrack response
                inventory_item = {
                    'item_id': str(item_id),
                    'product_name': item_info.get('productname', 'Unknown Product'),  # Use 'productname' from BioTrack
                    'quantity': item_info.get('remaining_quantity', 0),  # Use 'remaining_quantity' from BioTrack
                    'current_room_id': current_room_id,
                    'current_room_name': current_room_name,
                    'barcode_id': barcode_id,
                    'lab_results': lab_results
                }
                
                if lab_results:
                    items_with_lab_data += 1
                else:
                    items_without_lab_data += 1
                
                inventory_items.append(inventory_item)
                
            except Exception as e:
                logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
                continue
        
        # Create summary
        summary = {
            'total_items': len(inventory_items),
            'items_with_lab_data': items_with_lab_data,
            'items_without_lab_data': items_without_lab_data
        }
        
        logger.info(f"Generated inventory report: {summary['total_items']} items, "
                   f"{summary['items_with_lab_data']} with lab data")
        
        return jsonify({
            'success': True,
            'inventory_items': inventory_items,
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Error generating inventory report: {str(e)}")
        return jsonify({'error': f'Failed to generate inventory report: {str(e)}'}), 500

@app.route('/api/finished-goods-report')
@login_required
def get_finished_goods_report():
    """Get finished goods inventory report with filtering"""
    logger = logging.getLogger('app.finished_goods_report')
    logger.info("Generating finished goods inventory report")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
        
        # Authenticate with BioTrack
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Get inventory data
        logger.debug("Calling BioTrack API to fetch inventory")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            logger.error("Failed to retrieve inventory data from BioTrack")
            return jsonify({'error': 'Failed to retrieve inventory data'}), 500
        
        # Get room data for room name lookup
        logger.debug("Calling BioTrack API to fetch rooms")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Get selected rooms from preferences
        selected_rooms = []
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if preference:
            selected_rooms = [room_id.strip() for room_id in preference.preference_value.split(',') if room_id.strip()]
        
        # Define finished goods inventory types
        finished_goods_types = [22, 23, 24, 25, 28, 34, 35, 36, 37, 38, 39, 45]
        
        # Process inventory items with filtering
        inventory_items = []
        items_with_lab_data = 0
        items_without_lab_data = 0
        filtered_by_room = 0
        filtered_by_type = 0
        filtered_by_lab = 0
        
        for item_id, item_info in inventory_data.items():
            try:
                # Filter by selected rooms - use correct field name from BioTrack response
                current_room_id = str(item_info.get('currentroom', ''))
                if selected_rooms and current_room_id not in selected_rooms:
                    filtered_by_room += 1
                    continue
                
                # Filter by inventory type - use correct field name from BioTrack response
                inventory_type = item_info.get('inventorytype')
                if inventory_type not in finished_goods_types:
                    filtered_by_type += 1
                    continue
                
                # Get room name
                current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
                
                # Try to get lab data for this item - use correct field names from BioTrack response
                barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
                lab_results = None
                
                if barcode_id:
                    try:
                        logger.debug(f"Attempting QA check for barcode: {barcode_id}")
                        lab_results = get_inventory_qa_check(token, barcode_id)
                        if lab_results:
                            logger.debug(f"Found lab data for barcode {barcode_id}: {lab_results}")
                        else:
                            logger.debug(f"No lab data found for barcode {barcode_id}")
                    except Exception as e:
                        logger.warning(f"Error getting lab data for barcode {barcode_id}: {str(e)}")
                        lab_results = None
                
                # Filter by lab data availability
                if not lab_results:
                    filtered_by_lab += 1
                    continue
                
                # Create inventory item entry - use correct field names from BioTrack response
                inventory_item = {
                    'item_id': str(item_id),
                    'product_name': item_info.get('productname', 'Unknown Product'),  # Use 'productname' from BioTrack
                    'quantity': item_info.get('remaining_quantity', 0),  # Use 'remaining_quantity' from BioTrack
                    'current_room_id': current_room_id,
                    'current_room_name': current_room_name,
                    'barcode_id': barcode_id,
                    'inventory_type': inventory_type,
                    'lab_results': lab_results
                }
                
                items_with_lab_data += 1
                inventory_items.append(inventory_item)
                
            except Exception as e:
                logger.warning(f"Error processing inventory item {item_id}: {str(e)}")
                continue
        
        # Create summary
        summary = {
            'total_items': len(inventory_items),
            'items_with_lab_data': items_with_lab_data,
            'items_without_lab_data': items_without_lab_data,
            'filtered_by_room': filtered_by_room,
            'filtered_by_type': filtered_by_type,
            'filtered_by_lab': filtered_by_lab,
            'selected_rooms': selected_rooms
        }
        
        logger.info(f"Generated finished goods report: {summary['total_items']} items, "
                   f"{summary['items_with_lab_data']} with lab data")
        
        return jsonify({
            'success': True,
            'inventory_items': inventory_items,
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Failed to generate finished goods report: {str(e)}")
        return jsonify({'error': f'Failed to generate finished goods report: {str(e)}'}), 500

@app.route('/api/finished-goods-report/download')
@login_required
def download_finished_goods_report():
    """Download finished goods report as CSV file"""
    logger = logging.getLogger('app.finished_goods_report_download')
    logger.info("Generating downloadable finished goods report")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
        from io import StringIO
        import csv
        from datetime import datetime
        import time
        
        # Authenticate with BioTrack
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Get inventory data
        logger.debug("Calling BioTrack API to fetch inventory")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            logger.error("Failed to retrieve inventory data from BioTrack")
            return jsonify({'error': 'Failed to retrieve inventory data'}), 500
        
        logger.info(f"Retrieved {len(inventory_data)} inventory items from BioTrack")
        
        # Get room data for room name lookup
        logger.debug("Calling BioTrack API to fetch rooms")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Get selected rooms from preferences
        selected_rooms = []
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if preference:
            selected_rooms = [room_id.strip() for room_id in preference.preference_value.split(',') if room_id.strip()]
        
        logger.info(f"Selected rooms for filtering: {selected_rooms}")
        
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
                # Log progress every 50 items
                if i % 50 == 0:
                    elapsed = time.time() - start_time
                    logger.info(f"Processing item {i+1}/{len(pre_filtered_items)} (elapsed: {elapsed:.1f}s)")
                
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
        
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'finished_goods_report_{timestamp}.csv'
        
        total_time = time.time() - start_time
        logger.info(f"Generated finished goods report CSV: {items_processed} items with lab data, "
                   f"{items_without_lab_data} filtered out, processed in {total_time:.1f}s")
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error(f"Error generating finished goods report CSV: {str(e)}")
        return jsonify({'error': f'Failed to generate finished goods report: {str(e)}'}), 500

@app.route('/api/inventory-report/download')
@login_required
def download_inventory_report():
    """Download inventory report as CSV file"""
    logger = logging.getLogger('app.inventory_report_download')
    logger.info("Generating downloadable inventory report")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
        from io import StringIO
        import csv
        from datetime import datetime
        import time
        
        # Authenticate with BioTrack
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Get inventory data
        logger.debug("Calling BioTrack API to fetch inventory")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            logger.error("Failed to retrieve inventory data from BioTrack")
            return jsonify({'error': 'Failed to retrieve inventory data'}), 500
        
        # Get room data for room name lookup
        logger.debug("Calling BioTrack API to fetch rooms")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Create CSV content
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header (Item ID and Room ID are text fields to preserve formatting)
        writer.writerow([
            'Item ID (Text)', 'Product Name', 'Quantity', 'Current Room ID (Text)', 
            'Current Room Name', 'Lab Data Available', 'Total %', 'THCA %', 
            'THC %', 'CBDA %', 'CBD %'
        ])
        
        # Process inventory items with progress logging
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
                
                # Get room name - use correct field name from BioTrack response
                current_room_id = str(item_info.get('currentroom', ''))
                current_room_name = room_lookup.get(current_room_id, 'Unknown Room')
                
                # Try to get lab data for this item (ensure barcode_id is string)
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
                    str(item_id),  # Ensure item_id is string
                    item_info.get('productname', 'Unknown Product'),  # Use 'productname' from BioTrack
                    item_info.get('remaining_quantity', 0),  # Use 'remaining_quantity' from BioTrack
                    str(current_room_id),  # Ensure room_id is string
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
        
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'inventory_report_{timestamp}.csv'
        
        total_time = time.time() - start_time
        logger.info(f"Generated inventory report CSV: {items_processed} items "
                   f"({items_with_lab_data} with lab data, {items_without_lab_data} without), "
                   f"processed in {total_time:.1f}s")
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error(f"Error generating inventory report CSV: {str(e)}")
        return jsonify({'error': f'Failed to generate inventory report: {str(e)}'}), 500


@app.route('/api/test-qa-check/<barcode_id>')
@login_required
def test_qa_check(barcode_id):
    """Test endpoint to verify get_inventory_qa_check method"""
    logger = logging.getLogger('app.test_qa_check')
    logger.info(f"Testing QA check for barcode: {barcode_id}")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_qa_check
        
        # Authenticate with BioTrack
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        # Test QA check
        logger.debug(f"Calling BioTrack API to check QA for barcode: {barcode_id}")
        lab_results = get_inventory_qa_check(token, barcode_id)
        
        if lab_results:
            logger.info(f"QA check successful for barcode {barcode_id}: {lab_results}")
            return jsonify({
                'success': True,
                'barcode_id': barcode_id,
                'lab_results': lab_results
            })
        else:
            logger.info(f"No lab data found for barcode {barcode_id}")
            return jsonify({
                'success': True,
                'barcode_id': barcode_id,
                'lab_results': None,
                'message': 'No lab data available for this barcode'
            })
        
    except Exception as e:
        logger.error(f"Error testing QA check: {str(e)}")
        return jsonify({'error': f'Error testing QA check: {str(e)}'}), 500

@app.route('/api/finished-goods-report/test')
@login_required
def test_finished_goods_report():
    """Test endpoint to debug finished goods report without CSV generation"""
    logger = logging.getLogger('app.finished_goods_report_test')
    logger.info("Testing finished goods report data retrieval")
    
    try:
        from api.biotrack import get_auth_token, get_inventory_info, get_room_info, get_inventory_qa_check
        import time
        
        # Authenticate with BioTrack
        logger.debug("Attempting to authenticate with BioTrack")
        token = get_auth_token()
        if not token:
            logger.error("Failed to authenticate with BioTrack API")
            return jsonify({'error': 'Failed to authenticate with BioTrack API'}), 500
        
        logger.debug("Successfully authenticated with BioTrack")
        
        # Get inventory data
        logger.debug("Calling BioTrack API to fetch inventory")
        inventory_data = get_inventory_info(token)
        if not inventory_data:
            logger.error("Failed to retrieve inventory data from BioTrack")
            return jsonify({'error': 'Failed to retrieve inventory data'}), 500
        
        logger.info(f"Retrieved {len(inventory_data)} inventory items from BioTrack")
        
        # Get room data for room name lookup
        logger.debug("Calling BioTrack API to fetch rooms")
        room_data = get_room_info(token)
        room_lookup = {}
        if room_data:
            room_lookup = {room_id: room_info['name'] for room_id, room_info in room_data.items()}
        
        # Get selected rooms from preferences
        selected_rooms = []
        preference = GlobalPreference.query.filter_by(preference_key='finished_goods_rooms').first()
        if preference:
            selected_rooms = [room_id.strip() for room_id in preference.preference_value.split(',') if room_id.strip()]
        
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
        
        logger.info(f"Pre-filtered to {len(pre_filtered_items)} items matching room and type criteria")
        
        # Test a few items for lab data
        test_items = []
        start_time = time.time()
        
        for i, (item_id, item_info) in enumerate(pre_filtered_items[:10]):  # Test first 10 items
            try:
                barcode_id = str(item_info.get('barcode_id') or item_info.get('barcode') or item_id)
                lab_results = None
                
                if barcode_id:
                    try:
                        lab_results = get_inventory_qa_check(token, barcode_id)
                    except Exception as e:
                        logger.warning(f"Error getting lab data for barcode {barcode_id}: {str(e)}")
                        lab_results = None
                
                test_items.append({
                    'item_id': str(item_id),
                    'product_name': item_info.get('productname', 'Unknown Product'),
                    'inventory_type': item_info.get('inventorytype'),
                    'current_room': str(item_info.get('currentroom', '')),
                    'barcode_id': barcode_id,
                    'has_lab_data': lab_results is not None,
                    'lab_results': lab_results
                })
                
            except Exception as e:
                logger.warning(f"Error processing test item {item_id}: {str(e)}")
                continue
        
        total_time = time.time() - start_time
        
        return jsonify({
            'success': True,
            'total_inventory_items': len(inventory_data),
            'pre_filtered_items': len(pre_filtered_items),
            'selected_rooms': selected_rooms,
            'test_items_processed': len(test_items),
            'test_items': test_items,
            'processing_time_seconds': round(total_time, 2),
            'message': 'Test completed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error testing finished goods report: {str(e)}")
        return jsonify({'error': f'Failed to test finished goods report: {str(e)}'}), 500


@app.route('/help')
@login_required
def help():
    """Help and user guide page"""
    return render_template('help.html')

@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt file to prevent bot crawling"""
    return app.send_static_file('robots.txt')

if __name__ == '__main__':
    logger = logging.getLogger('app.main')
    logger.info("Starting Flask application", extra={
        'extra_fields': {
            'host': '0.0.0.0',
            'port': 5000,
            'debug_mode': True,
            'training_mode': get_training_mode()
        }
    })
    app.run(host='0.0.0.0', port=5000, debug=True) 