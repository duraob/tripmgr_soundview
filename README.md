# BioTrack-LeafTrade Trip Manager

## What is this application?

This is a **middleware application** that acts as a bridge between two important business systems:

- **LeafTrade**: Where customer orders are created and managed
- **BioTrack**: Where drivers, vehicles, and inventory are managed

Think of it as a smart coordinator that helps organize delivery trips by taking orders from LeafTrade and assigning drivers and vehicles from BioTrack.

## How does it work? (Simple Explanation)

1. **Order Collection**: The app pulls orders from LeafTrade that are ready for delivery
2. **Trip Building**: Users select which orders to group together into a delivery trip
3. **Resource Assignment**: The app assigns 2 drivers and 1 vehicle from BioTrack to each trip
4. **Route Planning**: Using Google Maps Routes API, the app creates turn-by-turn directions for delivery routes with proper timing
5. **Automation**: When a trip is finalized, the app automatically:
   - Moves inventory in BioTrack
   - Creates delivery manifests
   - Sends completion notifications via email

## Key Benefits

- **Saves Time**: No more manual coordination between systems
- **Reduces Errors**: Automated processes eliminate human mistakes
- **Better Planning**: AI-powered route generation with timing calculations
- **Real-time Updates**: Live status tracking of all trips
- **Audit Trail**: Complete record of all delivery activities

## Technical Setup

### Prerequisites
- Python 3.8 or higher
- PostgreSQL database (or SQLite for development)
- Access to LeafTrade and BioTrack APIs

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd trip-manager
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   # Copy the example file
   cp env_example.txt .env
   
   # Edit .env with your actual values
   # See env_example.txt for all required variables
   ```

4. **Initialize the database**
   ```bash
   python app.py
   ```

5. **Create a test user**
   ```bash
   python create_user.py
   ```

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the application**
   - Open your browser to: `http://localhost:5000`
   - Login with: `admin` / `admin123`

## Configuration Required

Before using the application, you need to configure:

### 1. Database Connection
- Set up PostgreSQL database (recommended for production)
- Or use SQLite for development (default)

### 2. API Keys
- **Google Maps API Key**: For route optimization
- **LeafTrade API**: For order data
- **BioTrack API**: For drivers, vehicles, and inventory

### 3. Email Settings
- SMTP server configuration for notifications
- List of email addresses to receive completion alerts

## Current Status

### ✅ Completed
- **Production-Ready Application**: Flask application with PostgreSQL database and comprehensive error handling
- **User Authentication**: Secure login/logout system with session management
- **Database Models**: Complete schema for trips, orders, drivers, vehicles, customers, and location mappings
- **Modern Web Interface**: Responsive design using Tailwind CSS with elegant, professional styling
- **Dashboard**: Real-time trip overview with status tracking
- **Trip Management**: Complete CRUD interface for trip creation, editing, and monitoring
- **API Integrations**: Production-ready LeafTrade and BioTrack API integrations with caching and fallback mechanisms
- **Location Mapping**: Modern interface for mapping LeafTrade customers to BioTrack vendors with room assignment
- **Configuration Management**: Dedicated config page for API data refresh and system status monitoring
- **Error Handling**: Comprehensive error handling with graceful degradation and user-friendly messaging

### 🚧 In Progress
- **Trip Execution**: Google Maps integration for route optimization and automated workflows
- **Email Notifications**: Automated completion alerts and status updates

### 📋 Next Steps
1. **Route Optimization**: Google Maps Routes API integration for turn-by-turn direction generation
2. **Automated Workflows**: Build BioTrack manifest creation and inventory movement automation
3. **Email Notifications**: Add completion alerts and status update system
4. **Production Deployment**: Set up monitoring, logging, and performance optimization

## Testing the Application

### Complete Application Test
1. **Start the application**: `python app.py`
2. **Access the application**: Open browser to `http://localhost:5000`
3. **Login**: Use admin credentials (`admin` / `admin123`)
4. **Test Navigation**: Navigate through all pages (Dashboard, Trips, New Trip, Config, Mapping)
5. **Test API Integration**: 
   - Go to Config page and refresh BioTrack data (Rooms, Vendors)
   - Refresh LeafTrade customers
   - Verify data appears in status cards
6. **Test Location Mapping**:
   - Go to Mapping page
   - Create new customer-vendor mappings
   - Test edit and delete functionality
   - Export mappings to CSV
7. **Test Trip Builder**:
   - Go to New Trip page
   - Load orders from LeafTrade
   - Select orders and assign resources
   - Create and save trips

### Database Verification
1. Run `python create_user.py` to create test user
2. Verify all database tables are created properly
3. Check that API data is being cached in the database

## File Structure

```
trip-manager/
├── app.py                 # Main Flask application
├── models.py             # Database models
├── requirements.txt      # Python dependencies
├── create_user.py       # Utility to create test user
├── env_example.txt      # Environment variables template
├── PRD.md              # Product Requirements Document
├── README.md           # This file
├── templates/          # HTML templates
│   ├── base.html      # Base template with navigation
│   ├── login.html     # Login page
│   ├── dashboard.html # Main dashboard
│   ├── trips.html     # Trip management
│   └── new_trip.html  # Trip creation (placeholder)
└── CONTEXT.md         # Development progress tracking
```

## Support

For technical support or questions about the application:
- Check the PRD.md file for detailed requirements
- Review CONTEXT.md for current development status
- Contact the development team for API integration assistance

---

**Note**: This application is designed for internal company use. Please ensure all API keys and credentials are kept secure and not shared publicly. 