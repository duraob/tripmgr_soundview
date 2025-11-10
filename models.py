from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, UTC
from utils.timezone import get_est_now

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # admin, user
    created_at = db.Column(db.DateTime, default=get_est_now)
    is_active = db.Column(db.Boolean, default=True)

class Trip(db.Model):
    """Trip model representing a delivery trip"""
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='pending')  # pending, completed
    date_created = db.Column(db.DateTime, default=get_est_now)
    date_transacted = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Trip execution details
    driver1_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    driver2_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'))
    departure_time = db.Column(db.DateTime)
    estimated_completion_time = db.Column(db.DateTime)
    route_data = db.Column(db.Text)  # JSON data from OpenAI route optimization (renamed from route_instructions)
    
    # Trip scheduling details
    approximate_start_time = db.Column(db.DateTime, nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    
    # Background execution status
    execution_status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    
    # Relationships
    orders = db.relationship('Order', backref='trip', lazy=True)
    trip_orders = db.relationship('TripOrder', backref='trip', lazy=True)
    driver1 = db.relationship('Driver', foreign_keys=[driver1_id])
    driver2 = db.relationship('Driver', foreign_keys=[driver2_id])
    vehicle = db.relationship('Vehicle', backref='trips', lazy=True)
    execution = db.relationship('TripExecution', backref='trip', uselist=False)

class Order(db.Model):
    """Order model representing orders from LeafTrade"""
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=True)
    leaftrade_order_id = db.Column(db.String(100), unique=True, nullable=False)
    invoice_id = db.Column(db.String(100))
    biotrack_manifest_id = db.Column(db.String(100))
    delivery_date = db.Column(db.Date)
    customer_name = db.Column(db.String(200))
    customer_contact = db.Column(db.String(200))
    customer_location = db.Column(db.String(500))
    order_status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)

class TripOrder(db.Model):
    """Trip orders junction table with sequence and room override"""
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    order_id = db.Column(db.String(255), nullable=False)  # LeafTrade order ID
    sequence_order = db.Column(db.Integer, nullable=False)
    room_override = db.Column(db.String(255))  # BioTrack room override
    manifest_id = db.Column(db.String(255))  # BioTrack manifest ID
    created_at = db.Column(db.DateTime, default=get_est_now)
    address = db.Column(db.String(500)) # Address of the dispensary
    
    # Vendor relationship for BioTrack integration
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    vendor = db.relationship('Vendor', backref='trip_orders')
    
    # Email delivery status columns
    manifest_attached = db.Column(db.Boolean, default=False)
    invoice_attached = db.Column(db.Boolean, default=False)
    email_ready = db.Column(db.Boolean, default=False)
    
    # Execution status tracking
    status = db.Column(db.String(20), default='pending')  # pending, sublotted, inventory_moved, manifested
    error_message = db.Column(db.Text, nullable=True)  # Order-specific error messages

class Driver(db.Model):
    """Driver model representing drivers from BioTrack"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Vehicle(db.Model):
    """Vehicle model representing vehicles from BioTrack"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Vendor(db.Model):
    """Vendor model representing BioTrack vendors"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_vendor_id = db.Column(db.String(100), unique=True)  # Location (license)
    name = db.Column(db.String(200), nullable=False)
    license_info = db.Column(db.String(500))
    ubi = db.Column(db.String(100))  # UBI for manifest creation
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)

class Room(db.Model):
    """Room model representing BioTrack rooms"""
    id = db.Column(db.Integer, primary_key=True)
    biotrack_room_id = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)

class Customer(db.Model):
    """Customer model representing LeafTrade customers"""
    id = db.Column(db.Integer, primary_key=True)
    leaftrade_customer_id = db.Column(db.String(100), unique=True)  # LeafTrade customer ID
    customer_name = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), nullable=False)  # Location name
    address = db.Column(db.String(500))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))
    country = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)

class LocationMapping(db.Model):
    """Mapping between LeafTrade dispensary locations and BioTrack vendors/rooms"""
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    leaftrade_dispensary_location_id = db.Column(db.Integer, nullable=False)  # LeafTrade dispensary location ID
    biotrack_vendor_id = db.Column(db.String(100), nullable=False)
    default_biotrack_room_id = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)
    
    # Relationships
    customer = db.relationship('Customer', backref='location_mappings')
    
    __table_args__ = (db.UniqueConstraint('leaftrade_dispensary_location_id', 'biotrack_vendor_id', name='unique_location_mapping'),)

class APIRefreshLog(db.Model):
    """Track when API data was last refreshed"""
    id = db.Column(db.Integer, primary_key=True)
    api_name = db.Column(db.String(50), nullable=False)  # 'drivers', 'vehicles', 'orders'
    last_refresh = db.Column(db.DateTime, default=get_est_now)
    records_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='success')  # 'success', 'error'
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_est_now)
    
    __table_args__ = (db.UniqueConstraint('api_name', name='unique_api_name'),)

class CustomerContact(db.Model):
    """Customer contacts attached to BioTrack vendors"""
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    contact_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    email_invoice = db.Column(db.Boolean, default=True)  # Default to True for backward compatibility
    email_manifest = db.Column(db.Boolean, default=True)  # Default to True for backward compatibility
    
    vendor = db.relationship('Vendor', backref='contacts')

class TripOrderDocument(db.Model):
    """Document storage for trip orders with compression"""
    __tablename__ = 'trip_order_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    trip_order_id = db.Column(db.Integer, db.ForeignKey('trip_order.id'), nullable=False)
    document_type = db.Column(db.String(20), nullable=False)  # 'manifest' or 'invoice'
    document_data = db.Column(db.LargeBinary, nullable=False)  # Compressed PDF
    uploaded_at = db.Column(db.DateTime, default=get_est_now)
    
    trip_order = db.relationship('TripOrder', backref='documents')

class InternalContact(db.Model):
    """Internal contacts that get CC'd on all outgoing emails"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_est_now)

# Junction table for many-to-many relationship between trips and drivers
trip_drivers = db.Table('trip_drivers',
    db.Column('trip_id', db.Integer, db.ForeignKey('trip.id'), primary_key=True),
    db.Column('driver_id', db.Integer, db.ForeignKey('driver.id'), primary_key=True)
)

class TripExecution(db.Model):
    """Trip execution tracking model"""
    __tablename__ = 'trip_executions'
    
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), primary_key=True)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    progress_message = db.Column(db.Text)
    job_id = db.Column(db.String(100))  # RQ job ID
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)
    started_at = db.Column(db.DateTime, nullable=True)  # When execute button was clicked
    completed_at = db.Column(db.DateTime, nullable=True)  # When execution finished
    general_error = db.Column(db.Text, nullable=True)  # General trip-level errors

class GlobalPreference(db.Model):
    """Global preferences model for system-wide settings"""
    id = db.Column(db.Integer, primary_key=True)
    preference_key = db.Column(db.String(255), unique=True, nullable=False)
    preference_value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=get_est_now)
    updated_at = db.Column(db.DateTime, default=get_est_now, onupdate=get_est_now)
