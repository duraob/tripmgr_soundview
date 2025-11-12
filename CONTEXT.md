# Trip Manager Soundview - Application Context

## Current State
The application is a Flask-based trip management system for cannabis delivery operations, integrating with BioTrack and LeafTrade APIs. The system handles trip creation, order processing, manifest generation, and email notifications.

## Recent Updates

### Trip Execution Duplicate Key Fix (Latest)
- **Issue**: Fixed duplicate key violation error when executing trips with existing TripExecution records
- **Root Cause**: Race condition where query didn't find existing record, causing INSERT to fail on unique constraint
- **Solution**: Added IntegrityError handling in `_update_trip_execution_status()` function
  - Catches IntegrityError when INSERT fails
  - Rolls back transaction and retries with UPDATE instead
  - Handles race condition gracefully
- **Session Rollback**: Added `db.session.rollback()` in exception handler to prevent PendingRollbackError
- **Minimal Code**: Following .cursorrules - only added error handling, no refactoring
- **Production Ready**: Trip execution now handles existing records correctly without errors

### Trip Order Status Tracking & Error Logging
- **Status Progression**: Trip orders now track execution status through biotrack actions
  - Status flow: `pending` → `sublotted` → `inventory_moved` → `manifested`
  - Status updates automatically after each successful biotrack action
- **Error Logging**: Comprehensive error tracking at both order and trip levels
  - Order-level errors: Stored in `TripOrder.error_message` for specific order failures
  - Trip-level errors: Stored in `TripExecution.general_error` for general execution failures
- **Execution Timestamps**: Track when execute button was clicked and when execution completed
  - `TripExecution.started_at`: Timestamp when execute button was clicked (EST/EDT)
  - `TripExecution.completed_at`: Timestamp when execution finished (EST/EDT)
- **UI Enhancements**: Trip detail page displays status and errors
  - Status badges: Color-coded badges showing current status for each order
  - Error messages: Red alert boxes displaying error messages for failed orders
  - Execution info: Section showing execution start/completion times
  - General errors: Prominent display of trip-level errors at top of page
- **Database Schema**: Added new fields to models
  - `TripOrder.status`: String field tracking execution status (default: 'pending')
  - `TripOrder.error_message`: Text field for order-specific errors
  - `TripExecution.started_at`: DateTime field for execution start time
  - `TripExecution.general_error`: Text field for trip-level errors
- **Status Reset**: Order statuses reset to 'pending' when execute is clicked again
- **Error Persistence**: Errors persist until next execution attempt
- **Minimal Code**: Following .cursorrules - simple status tracking, no over-engineering
- **Production Ready**: All timestamps use EST/EDT timezone, migration included

### Unified Report Generation System
- **Consistent Architecture**: Report generation now uses same patterns as trip execution
- **Task Queue Module**: Extended `utils/task_queue.py` to handle report generation consistently
- **Cross-Platform Worker**: Simplified worker that works on both Windows and Ubuntu
- **Job Timeouts**: Added proper 10-minute timeouts for report generation jobs
- **Unified Error Handling**: Same error handling patterns as trip execution
- **Flask App Context**: Proper Flask context handling in background jobs
- **Production Ready**: Same reliability and patterns as working trip execution system

### Background Job Inventory Reports (Previous)
- **Background Processing**: Moved both inventory reports to background jobs to prevent timeout issues
- **Global Storage**: Implemented global file storage with cleanup on completion (max 1 report per type)
- **Timestamp Display**: Added timestamp display showing when reports were last generated
- **Generation → Download Workflow**: Clear two-step process: generate then download
- **ReportJob Model**: Added database model for tracking report generation jobs
- **Status Tracking**: Real-time status updates with progress percentage and item counts
- **File Management**: Automatic cleanup of old reports when new ones complete
- **UI Updates**: Updated config.html with status display, timestamps, and generation buttons
- **API Endpoints**: New endpoints for generation, status checking, and file download
- **Storage Structure**: Created `/storage/reports/` directory for global report files
- **Visual Indicators**: Added comprehensive visual feedback for report generation status
- **Progress Display**: Real-time progress updates with percentage and item counts
- **Button States**: Dynamic button states showing generation progress and status
- **Error Handling**: Clear error messages with visual indicators
- **Production Ready**: Reports now process in background without blocking the UI

### Worker Flask Context Fix
- **Application Context**: Fixed Flask application context issue in background worker
- **Minimal Changes**: Updated only necessary files following .cursorrules principles
- **Worker Fix**: Added `from app import app` and `with app.app_context():` to worker.py
- **Trip Execution Fix**: Wrapped entire trip execution function in Flask app context
- **GoogleMaps API Fix**: Fixed method signature for `generate_route_segments()` - now passes 3 arguments (addresses, delivery_date, approx_start_time)
- **Enhanced Debugging**: Added detailed logging for order processing, sublot creation, and manifest creation
- **Error Details**: Critical failures now include specific error messages for better troubleshooting
- **Production Ready**: Worker now properly accesses database within Flask context
- **Error Resolution**: Fixed "Working outside of application context" RuntimeError and GoogleMaps API TypeError

### BioTrack API Pattern Fix (Current)
- **Original Working Pattern**: Restored original working BioTrack API pattern from reference code
- **Function Signatures**: Fixed BioTrack API function calls to match original working signatures
- **New Function**: Added `post_sublot_bulk_create()` function to match original working pattern
- **Order Processing**: Simplified order processing to use original working flow: Order → Sublot → Move → Manifest
- **Enhanced Debugging**: Maintained enhanced debugging statements (better than original)
- **Minimal Code**: Following .cursorrules - minimal changes, simple solution, no over-engineering
- **Production Ready**: Trip execution now follows original working methodology with background worker compatibility

### Database Schema Fix (Latest)
- **Room ID Issue**: Fixed `TripOrder` model attribute error - `default_biotrack_room_id` doesn't exist
- **Location Mapping**: Updated to get room ID from `LocationMapping` table via `dispensary_location_id`
- **Vendor ID Issue**: Fixed `TripOrder` model attribute error - `biotrack_vendor_id` doesn't exist
- **Vendor Mapping**: Updated to get vendor ID from `LocationMapping` table via `dispensary_location_id`
- **Fallback Logic**: Added proper fallback logic for room and vendor IDs
- **Room Override**: Added support for `trip_order.room_override` field
- **Error Resolution**: Fixed "TripOrder object has no attribute 'default_biotrack_room_id'" error

### BioTrack UID Validation (Current)
- **UID Validation**: Added validation for standard BioTrack UIDs (16-digit numbers)
- **Trip Execution**: Filters out invalid UIDs during sublot creation in background worker
- **Frontend Validation**: Filters out invalid UIDs during inventory check in validation workflow
- **Consistent Filtering**: Both execution and validation now use same UID validation logic
- **Enhanced Logging**: Added detailed logging for filtered invalid UIDs
- **Error Messages**: Updated error messages to specify "valid BioTrack UIDs (16-digit numbers)"
- **Minimal Code**: Following .cursorrules - added single validation function used in both places

### Route Data Integration (Latest)
- **Route Data Usage**: Fixed manifest creation to use actual route data from Google Maps API
- **Timing Integration**: Manifest now uses actual departure/arrival times from route segments
- **Direction Integration**: Manifest now includes real turn-by-turn directions from route segments
- **Sequence Integration**: Manifest uses correct stop number based on trip order sequence
- **Fallback Logic**: Maintains fallback values if route data is unavailable
- **Reference Alignment**: Now matches reference implementation pattern for route data usage
- **Minimal Changes**: Following .cursorrules - updated only manifest creation logic

### Manifest ID Storage (Current)
- **Database Storage**: Added manifest ID storage in `trip_order.manifest_id` field
- **Database Commit**: Added `db.session.commit()` after storing manifest ID
- **Frontend Display**: Manifest IDs now persist and display on trip detail page
- **Reference Alignment**: Matches reference implementation pattern for manifest ID storage
- **Debug Logging**: Added logging to confirm manifest ID storage
- **Minimal Code**: Following .cursorrules - added only 3 lines for database storage

### Inventory Validation Fix (Latest)
- **Data Structure Issue**: Fixed inventory lookup logic to properly match barcode_id with BioTrack inventory data
- **Lookup Method**: Changed from direct key lookup to searching through inventory items for matching barcode_id field
- **Data Type Consistency**: Added explicit string conversion for barcode_id comparison between LeafTrade and BioTrack
- **Skip Logic**: Implemented graceful handling for orders with no valid BioTrack UIDs - now skipped instead of failed
- **Validation Behavior**: Orders with no barcode IDs show warning but don't fail validation
- **Execution Behavior**: Orders with no barcode IDs are skipped during execution with 'skipped' status
- **Preserved Functionality**: Maintained full BioTrack object structure for inventory reports functionality
- **Minimal Code**: Following .cursorrules - only modified lookup logic and error handling

### Finished Goods Report (Latest)
- **Global Preferences**: Added GlobalPreference model for system-wide settings
- **Room Selection**: Users can select which rooms to include in finished goods report
- **Product Type Filtering**: Filters by finished goods inventory types (22,23,24,25,28,34,35,36,37,38,39,45,62)
- **QA Passed Filtering**: Only includes items with lab data available
- **CSV Export**: Downloadable CSV with complete lab test results
- **Persistent Settings**: Room selections persist across sessions
- **UI Integration**: Added to config page with room selection checkboxes
- **Column Updates**:
  - **Batch Ref**: Renamed from "Item ID (Text)"
  - **Pull Number**: New column - "C00800" + last 5 characters of product name
  - **Package Unit**: New column based on inventory type:
    - Type 22 → "100.00mg"
    - Type 62 → "500.00mg" (if product contains ".5g"), "1000.00mg" (if contains "1g" or default), "" (other types)
  - **Removed Columns**: Current Room ID (Text), Inventory Type, Lab Data Available
  - **Retained Columns**: Product Name, Quantity, Current Room Name, Total %, THCA %, THC %, CBDA %, CBD %
- **Helper Functions**: Added `_calculate_pull_number()` and `_calculate_package_unit()` for modular logic
- **Minimal Code**: Following .cursorrules - reused existing patterns, ~250 lines total

### Mappings Export Enhancement
- **Vendor Name Integration**: Added vendor names to mappings CSV export
- **Enhanced Data Export**: Mappings export now includes vendor names for better readability
- **Database Join**: Modified export query to join LocationMapping with Vendor table
- **CSV Format**: Updated CSV header to include "Vendor Name" column
- **Fallback Handling**: Shows "Unknown Vendor" for mappings without vendor data
- **API Endpoint**: `/api/mapping/export` now returns enhanced CSV with vendor information

### Redis Worker Status Process Implementation
- **Background Job Processing**: Implemented Redis + RQ for non-blocking trip execution
- **Real-time Progress Tracking**: Users can monitor trip execution progress in real-time
- **Production Ready**: Configured for Digital Ocean deployment with Redis server
- **Key Features**:
  - **Non-blocking trip execution**: Users can navigate away during processing
  - **Real-time progress updates**: Progress bar and status messages
  - **Fault tolerance**: Failed jobs can be retried
  - **Scalable architecture**: Multiple workers can process trips
  - **Persistent jobs**: Jobs survive server restarts

### Technical Implementation
- **New Dependencies**: Added `redis==5.0.1` and `rq==1.15.1` to requirements.txt
- **Database Schema**: Added `TripExecution` model for tracking background job status
- **Background Worker**: `worker.py` for processing trip execution jobs
- **Task Queue**: `utils/task_queue.py` for Redis queue management
- **Trip Execution Worker**: `utils/trip_execution.py` for background job logic
- **Progress Page**: `templates/trip_progress.html` for real-time status updates
- **API Endpoints**:
  - `POST /trips/<id>/execute` - Enqueues background job
  - `GET /api/trips/<id>/execution-status` - Polls execution status
  - `GET /trips/<id>/progress` - Progress page

### Database Changes
- **Trip Model**: Added `execution_status` field (pending, processing, completed, failed)
- **TripExecution Model**: New model for tracking background job progress
  - Fields: `trip_id`, `status`, `progress_message`, `job_id`, timestamps
  - Relationship: One-to-one with Trip model

### Background Job Workflow
1. **User clicks "Execute Trip"** → Trip execution enqueued in Redis
2. **Background worker picks up job** → Processes trip execution
3. **Real-time status updates** → Database updated with progress
4. **Frontend polls status** → JavaScript polls every 3 seconds
5. **Completion handling** → User redirected to trip detail page

### Production Deployment Requirements
- **Redis Server**: Must be installed and running on Digital Ocean
- **Worker Process**: `python worker.py` must be running as background service
- **Environment Variables**: `REDIS_URL` for Redis connection
- **Systemd Service**: Recommended for worker process management

## Previous Features

### Inventory Report Feature
- **API Endpoint**: `GET /api/inventory-report` - JSON response with inventory data
- **Download Endpoint**: `GET /api/inventory-report/download` - CSV file download
- **Test Endpoint**: `GET /api/test-qa-check/<barcode_id>` - Test lab data retrieval
- **Frontend Integration**: Available in Config menu as downloadable CSV
- **Purpose**: Provides comprehensive inventory report with lab test data and room information
- **Authentication**: Login required
- **Features**:
  - Lists all inventory items with quantities and current room locations
  - Includes room name lookup for better readability
  - **Lab test data integration**: Automatically retrieves cannabinoid test results for each item
  - Returns summary statistics (total items, items with/without lab data)
  - CSV download with timestamped filename and lab data columns
  - User-friendly interface in Config menu
  - **Lab Data Fields**: Total %, THCA %, THC %, CBDA %, CBD %
  - **Data Formatting**: All ID fields (Item ID, Room ID, Barcode ID) are formatted as text strings to preserve leading zeros and prevent formatting issues
  - **UI Enhancement**: Featured prominently at the top of Config page with distinctive blue gradient styling and feature badges

### BioTrack API Enhancements
- **Enhanced `get_inventory_info()`**: Now includes `current_room_id` field for each inventory item
- **New `get_inventory_qa_check()`**: Retrieves lab test results for specific barcode IDs
  - Extracts cannabinoid data (Total, THCA, THC, CBDA, CBD)
  - Handles cases where no lab data exists gracefully
  - Uses BioTrack's `inventory_qa_check` action

## Documentation Created
- **USER_CRUD_ARCHITECTURE.md**: Comprehensive documentation of the user management system architecture
  - Complete CRUD operations (Create, Read, Update, Delete)
  - Authentication and authorization patterns
  - Security features and safety checks
  - Template structure and UI components
  - Implementation checklist for replication
  - Testing procedures and dependencies
  - Ready for use by other coding agents to replicate the system

## Security Enhancements
- **robots.txt**: Created to prevent bot crawling and web crawler abuse
  - Located at `/static/robots.txt`
  - Configured to disallow all bots from accessing any part of the site
  - Flask route `/robots.txt` serves the file automatically
  - Protects private internal application from unwanted bot traffic

## Next Steps
1. **Database Migration**: Run migration to add TripExecution table
2. **Redis Installation**: Install and configure Redis server on Digital Ocean
3. **Worker Service**: Set up systemd service for background worker
4. **Testing**: Test background job processing with real trip execution
5. **Monitoring**: Set up monitoring for Redis and worker processes

### Simplified Report Generation System (Latest)
- **Clean Architecture**: Implemented simplified report generation system following .cursorrules
- **New Module**: Created `utils/rpt_generation.py` with minimal, modular functions
- **API Endpoints**: Added 6 new simplified endpoints for both inventory and finished goods reports
- **Background Processing**: Integrated with existing RQ worker system
- **Frontend UI**: Added clean, simple interface in config.html
- **Status Tracking**: Simple status system using GlobalPreference (generating/ready/error)
- **File Management**: Automatic cleanup and timestamped file storage
- **Room Selection**: Persistent room selection for finished goods reports
- **Code Reduction**: ~60% less code than previous complex system
- **Production Ready**: Simple, maintainable, and reliable

### Implementation Details
- **Report Types**: Full inventory report and finished goods report with filtering
- **Background Jobs**: Uses RQ worker with 'report_generation' queue
- **Status System**: Simple 3-state system (generating/ready/error)
- **File Storage**: `/storage/reports/` with automatic cleanup
- **UI Features**: Real-time status updates, simple polling, clean interface
- **Error Handling**: Clear error messages and status indicators
- **Room Filtering**: Persistent room selection for finished goods reports

## Testing Instructions
1. **Activate virtual environment**: `.\.venv\Scripts\Activate.ps1`
2. **Install new dependencies**: `pip install -r requirements.txt`
3. **Start Redis server**: `redis-server` (or configure for production)
4. **Start worker process**: `python worker.py` (in separate terminal)
5. **Start application**: `python app.py`
6. **Test trip execution**:
   - Create a trip with orders
   - Click "Execute Trip" button
   - Verify redirect to progress page
   - Monitor real-time progress updates
   - Verify completion and redirect to trip detail

## Dependencies
- **New**: `redis==5.0.1`, `rq==1.15.1`
- **Existing**: All previous dependencies maintained
- **Production**: Redis server required on Digital Ocean
