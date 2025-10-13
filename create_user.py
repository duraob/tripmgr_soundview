#!/usr/bin/env python3
"""
Utility script to create a test user for the Trip Manager application.
Run this script to create an initial admin user.
"""

from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def create_test_user():
    """Create a test user for development"""
    with app.app_context():
        # Check if user already exists
        existing_user = User.query.filter_by(username='admin').first()
        if existing_user:
            print("Admin user already exists!")
            return
        
        # Create new admin user
        admin_user = User(
            username='admin',
            email='admin@company.com',
            password_hash=generate_password_hash('admin123'),
            role='admin'
        )
        
        db.session.add(admin_user)
        db.session.commit()
        
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("Please change the password after first login!")

if __name__ == '__main__':
    create_test_user() 