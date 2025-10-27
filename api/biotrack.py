"""
BioTrack API Integration Module

This module handles all interactions with the BioTrack API including:
- Driver and vehicle management
- Inventory movement transactions
- Manifest creation and management
- Room/location management
- Route optimization integration

Production-ready features:
- Comprehensive error handling and logging
- Retry mechanisms with exponential backoff
- Input validation and sanitization
- Rate limiting considerations
- Proper exception handling
- Type hints and documentation
"""

import os
import logging
import time
import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date
from functools import wraps
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Configuration constants
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
REQUEST_TIMEOUT = 30  # seconds

# Environment variables
BIOTRACK_API_URL = os.getenv("BIOTRACK_API_URL")
BIOTRACK_USERNAME = os.getenv("BIOTRACK_USERNAME")
BIOTRACK_PASSWORD = os.getenv("BIOTRACK_PASSWORD")
BIOTRACK_UBI = os.getenv("BIOTRACK_UBI")


def validate_config() -> bool:
    """Validate that all required environment variables are set."""
    required_vars = {
        "BIOTRACK_API_URL": BIOTRACK_API_URL,
        "BIOTRACK_USERNAME": BIOTRACK_USERNAME,
        "BIOTRACK_PASSWORD": BIOTRACK_PASSWORD,
        "BIOTRACK_UBI": BIOTRACK_UBI
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    return True


def retry_on_failure(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator to retry API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RequestException, Timeout, ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"API call failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{func.__name__} - {str(e)}. Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"API call failed after {max_retries + 1} attempts: "
                            f"{func.__name__} - {str(e)}"
                        )
                        raise last_exception
            
            return None
        return wrapper
    return decorator


def validate_token(token: str) -> bool:
    """Validate that a token is provided and not empty."""
    if not token or not isinstance(token, str):
        logger.error("Invalid or missing authentication token")
        return False
    return True


def validate_training_mode(training: str) -> str:
    """Validate and normalize training mode parameter."""
    if training not in ["0", "1"]:
        logger.warning(f"Invalid training mode '{training}', defaulting to '0'")
        return "0"
    return training


@retry_on_failure()
def _make_api_request(data: Dict[str, Any], action: str) -> Optional[Dict[str, Any]]:
    """
    Make a standardized API request to BioTrack with proper error handling.
    
    Args:
        data: Request payload
        action: API action being performed (for logging)
    
    Returns:
        Response JSON data or None if failed
    """
    if not validate_config():
        raise ValueError("BioTrack configuration is invalid")
    
    try:
        logger.debug(f"Making BioTrack API request: {action}")
        # BioTrack API expects form data, not JSON
        response = requests.post(
            BIOTRACK_API_URL,
            json=data,
            timeout=REQUEST_TIMEOUT
        )
        
        response.raise_for_status()
        
        try:
            json_data = response.json()
            logger.debug(f"BioTrack API response for {action}: {json_data}")
            return json_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for {action}: {e}")
            raise
            
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error for {action}: {e.response.status_code} - {e.response.text}")
        raise
    except Timeout:
        logger.error(f"Request timeout for {action}")
        raise
    except ConnectionError as e:
        logger.error(f"Connection error for {action}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error for {action}: {e}")
        raise


def get_auth_token() -> Optional[str]:
    """
    Authenticate with BioTrack API and retrieve session token.
    
    Returns:
        Session token string or None if authentication failed
    """
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    # Log authentication attempt details (without exposing credentials)
    logger.debug(f"Attempting BioTrack authentication with training mode: {training}")
    logger.debug(f"Username provided: {bool(BIOTRACK_USERNAME)}")
    logger.debug(f"Password provided: {bool(BIOTRACK_PASSWORD)}")
    logger.debug(f"License number provided: {bool(BIOTRACK_UBI)}")
    
    data = {
        "API": "4.0",
        "action": "login",
        "username": BIOTRACK_USERNAME,
        "password": BIOTRACK_PASSWORD,
        "license_number": BIOTRACK_UBI
    }
    
    try:
        response_data = _make_api_request(data, "login")
        
        if response_data and "sessionid" in response_data:
            token = response_data["sessionid"]
            logger.info("Successfully authenticated with BioTrack API")
            return token
        else:
            logger.error("Authentication response missing sessionid")
            logger.error(f"Full authentication response: {response_data}")
            return None
            
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return None


def get_driver_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve driver information from BioTrack.
    
    Args:
        token: Authentication token
    
    Returns:
        Dictionary mapping driver_id to driver details or None if failed
    """
    if not validate_token(token):
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "sync_employee",
        "sessionid": token,
        "active": "1",
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "sync_employee")
        
        if response_data and "employee" in response_data:
            drivers = response_data["employee"]
            driver_dict = {}
            
            for driver in drivers:
                try:
                    driver_id = driver.get("employee_id")
                    # Convert driver_id to string to match database schema
                    driver_id = str(driver_id) if driver_id is not None else None
                    driver_name = driver.get("employee_name", "Unknown")
                    # 'deleted' field is 0 for active drivers, 1 for deleted (same as vehicles)
                    driver_is_active = 1 if driver.get("deleted") == 0 else 0
                    
                    if driver_id:
                        driver_dict[driver_id] = {
                            "name": driver_name,
                            "is_active": driver_is_active
                        }
                except KeyError as e:
                    logger.warning(f"Driver data missing required field: {e}")
                    continue
            
            logger.info(f"Retrieved {len(driver_dict)} drivers from BioTrack")
            return driver_dict
        else:
            logger.error("Driver info response missing 'employee' field")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get driver info: {e}")
        return None


def get_vehicle_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve vehicle information from BioTrack.
    
    Args:
        token: Authentication token
    
    Returns:
        Dictionary mapping vehicle_id to vehicle details or None if failed
    """
    if not validate_token(token):
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "sync_vehicle",
        "sessionid": token,
        "active": "1",
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "sync_vehicle")
        
        if response_data and "vehicle" in response_data:
            vehicles = response_data["vehicle"]
            vehicle_dict = {}
            
            logger.debug(f"Raw vehicle response: {vehicles}")
            
            for vehicle in vehicles:
                try:
                    logger.debug(f"Processing vehicle: {vehicle}")
                    vehicle_id = vehicle.get("vehicle_id")
                    # Convert vehicle_id to string to match database schema
                    vehicle_id = str(vehicle_id) if vehicle_id is not None else None
                    # BioTrack API returns 'nickname' field, not 'vehicle_name'
                    vehicle_name = vehicle.get("nickname", "Unknown")
                    # 'deleted' field is 0 for active vehicles, 1 for deleted
                    vehicle_is_active = 1 if vehicle.get("deleted") == 0 else 0
                    
                    logger.debug(f"Vehicle {vehicle_id}: name='{vehicle_name}', active={vehicle_is_active}")
                    
                    if vehicle_id:
                        vehicle_dict[vehicle_id] = {
                            "name": vehicle_name,
                            "is_active": vehicle_is_active
                        }
                except KeyError as e:
                    logger.warning(f"Vehicle data missing required field: {e}")
                    continue
            
            logger.info(f"Retrieved {len(vehicle_dict)} vehicles from BioTrack")
            return vehicle_dict
        else:
            logger.error("Vehicle info response missing 'vehicle' field")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get vehicle info: {e}")
        return None


def get_vendor_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve vendor information from BioTrack.
    
    Args:
        token: Authentication token
    
    Returns:
        Dictionary mapping location (license) to vendor details or None if failed.
        Each vendor detail contains: name, ubi, license
    """
    if not validate_token(token):
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "sync_vendor",
        "sessionid": token,
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "vendor_info")
        
        if response_data and "vendor" in response_data:
            vendors = response_data["vendor"]
            vendor_dict = {}
            
            for vendor in vendors:
                try:
                    # Only process vendors that are not deleted AND have retail flag == 1
                    # BioTrack API returns 'deleted' as integer (0=active, 1=deleted)
                    if vendor.get("deleted") == 0 and vendor.get("retail") == 1:
                        vendor_location = vendor.get("location", "")
                        vendor_name = vendor.get("name", "Unknown")
                        vendor_ubi = vendor.get("ubi", "")
                        
                        if vendor_location:
                            vendor_dict[vendor_location] = {
                                "name": vendor_name,
                                "ubi": vendor_ubi,
                                "license": vendor_location
                            }
                except KeyError as e:
                    logger.warning(f"Vendor data missing required field: {e}")
                    continue
            
            logger.info(f"Retrieved {len(vendor_dict)} vendors from BioTrack")
            return vendor_dict
        else:
            logger.error("Vendor info response missing 'vendor' field")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get vendor info: {e}")
        return None


def get_room_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve room/location information from BioTrack.
    
    Args:
        token: Authentication token
    
    Returns:
        Dictionary mapping room_id to room details or None if failed
    """
    if not validate_token(token):
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "sync_inventory_room",
        "sessionid": token,
        "active": "1",
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "room_info")
        
        if response_data and "inventory_room" in response_data:
            rooms = response_data["inventory_room"]
            room_dict = {}
            
            for room in rooms:
                try:
                    room_id = room.get("roomid")
                    room_name = room.get("name", "Unknown")
                    # 'deleted' field is 0 for active rooms, 1 for deleted (same as drivers/vehicles)
                    room_is_active = 1 if room.get("deleted") == 0 else 0
                    
                    if room_id:
                        room_dict[room_id] = {
                            "name": room_name,
                            "is_active": room_is_active
                        }
                except KeyError as e:
                    logger.warning(f"Room data missing required field: {e}")
                    continue
            
            logger.info(f"Retrieved {len(room_dict)} rooms from BioTrack")
            return room_dict
        else:
            logger.error("Room info response missing 'inventory_room' field")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get room info: {e}")
        return None


def get_inventory_info(token: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Retrieve inventory information from BioTrack.
    
    Args:
        token: Authentication token
    
    Returns:
        Dictionary mapping item_id to inventory details or None if failed
    """
    if not validate_token(token):
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "sync_inventory",
        "sessionid": token,
        "active": "1",
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "inventory_info")
        
        if response_data and "inventory" in response_data:
            inventory = response_data["inventory"]
            inventory_dict = {}
            
            for item in inventory:
                try:
                    item_id = item.get("id")
                    item_name = item.get("productname", "Unknown")
                    raw_quantity = item.get("remaining_quantity", "0")
                    current_room = item.get("currentroom", "")
                    
                    # Ensure quantity is consistently typed as integer
                    if raw_quantity is not None:
                        try:
                            item_quantity = int(float(raw_quantity))  # Handle both string and float inputs
                        except (ValueError, TypeError):
                            item_quantity = 0
                    else:
                        item_quantity = 0
                    
                    if item_id:
                        inventory_dict[item_id] = {
                            "name": item_name,
                            "quantity": item_quantity,
                            "current_room_id": current_room
                        }
                except KeyError as e:
                    logger.warning(f"Inventory item data missing required field: {e}")
                    continue
            
            logger.info(f"Retrieved {len(inventory_dict)} inventory items from BioTrack")
            return inventory_dict
        else:
            logger.error("Inventory info response missing 'inventory' field")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get inventory info: {e}")
        return None


def get_inventory_qa_check(token: str, barcode_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve lab test results for a specific inventory item from BioTrack.
    
    Args:
        token: Authentication token
        barcode_id: Barcode ID of the inventory item
    
    Returns:
        Dictionary with lab test results or None if failed/no data
    """
    if not validate_token(token):
        return None
    
    if not barcode_id:
        logger.error("Barcode ID is required for QA check")
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    data = {
        "API": "4.0",
        "action": "inventory_qa_check_all",
        "sessionid": token,
        "barcodeid": barcode_id
    }
    
    try:
        logger.debug(f"Making QA check request for barcode: {barcode_id}")
        response_data = _make_api_request(data, "inventory_qa_check_all")
        
        # Log the full response for debugging
        logger.debug(f"QA check response for barcode {barcode_id}: {response_data}")
        
        if response_data:
            # Check for success in different possible formats
            success = response_data.get("success")
            
            logger.debug(f"Success field: {success}")
            
            # Try different success indicators
            if (success == 1 or success == "1"):
                # Extract lab test data from the response - new structure has 'data' array
                data_array = response_data.get("data", [])
                logger.debug(f"Data array found: {data_array}")
                
                if data_array:
                    # Get the first item from the data array
                    first_item = data_array[0]
                    test_data = first_item.get("test", [])
                    logger.debug(f"Test data found: {test_data}")
                    
                    lab_results = {}
                    
                    # Look for cannabinoid test results (type 2)
                    for test in test_data:
                        if test.get("type") == 2:
                            lab_results = {
                                "total": test.get("Total"),
                                "thca": test.get("THCA"),
                                "thc": test.get("THC"),
                                "cbda": test.get("CBDA"),
                                "cbd": test.get("CBD")
                            }
                            logger.debug(f"Found cannabinoid data: {lab_results}")
                            break
                    
                    # Only return results if we found cannabinoid data
                    if lab_results and any(lab_results.values()):
                        logger.debug(f"Retrieved lab results for barcode {barcode_id}: {lab_results}")
                        return lab_results
                    else:
                        logger.debug(f"No cannabinoid lab data found for barcode {barcode_id}")
                        return None
                else:
                    logger.debug(f"No data array found for barcode {barcode_id}")
                    return None
            else:
                logger.debug(f"QA check not successful for barcode {barcode_id}. Success: {success}")
                return None
        else:
            logger.debug(f"No response data for barcode {barcode_id}")
            return None
            
    except Exception as e:
        logger.warning(f"Failed to get QA check for barcode {barcode_id}: {e}")
        return None


def post_sublot(
    token: str, 
    sublot_id: str, 
    move_info: List[Dict[str, str]]
) -> Optional[List[str]]:
    """
    Create inventory sublot splits in BioTrack.

    Description: This function is used to create inventory sublot splits in BioTrack.
    It is used to split an inventory item into multiple sublots.
    It is used to create a new sublot for each item in the move_info list.
    
    Example Input: 
    {
        "API": "4.0",
        "action": "inventory_split",
        "data": [
            {
                "barcodeid": "6853296789574117",
                "remove_quantity": "693.00"
            },
            {
                "barcodeid": "6853296789574118",
                "remove_quantity": "252.00"
            }
        ]
    }

    Example Output:
    {
        "sessiontime": "1384476925",
        "barcode_id": [
            "6853296789574115",
            "6853296789574116"
        ],
        "success": "1",
        "transactionid": "3312"
    }

    Args:
        token: Authentication token
        sublot_id: ID of the sublot to split
        move_info: List of dictionaries with "barcodeid" and "remove_quantity"
    
    Returns:
        List of new barcode IDs or None if failed
    """
    if not validate_token(token):
        return None
    
    if not sublot_id or not move_info:
        logger.error("Invalid sublot_id or move_info provided")
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    # Validate move_info structure
    for item in move_info:
        if not isinstance(item, dict) or "barcodeid" not in item or "remove_quantity" not in item:
            logger.error("Invalid move_info structure - each item must have 'barcodeid' and 'remove_quantity'")
            return None
    
    data = {
        "API": "4.0",
        "action": "inventory_split",
        "sessionid": token,
        "sublot_id": sublot_id,
        "data": move_info,
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "sublot_split")
        
        if response_data and str(response_data.get("success")) == "1":
            sublot_ids = response_data.get("barcode_id", [])
            logger.info(f"Successfully created {len(sublot_ids)} sublot splits")
            return sublot_ids
        else:
            logger.error(f"Sublot split failed: {response_data}")
            # Return the detailed error information for better user feedback
            return {
                'success': False,
                'error': response_data.get('error', 'Unknown BioTrack error'),
                'errorcode': response_data.get('errorcode', 'Unknown'),
                'details': response_data
            }
            
    except Exception as e:
        logger.error(f"Failed to post sublot: {e}")
        return None


def post_sublot_move(
    token: str, 
    move_info: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """
    Move inventory sublots between rooms in BioTrack.

    Description: The inventory_move function will update the current room for the specified inventory items. 
    Essentially, it allows a user to move inventory from one room to another.
    
    Example Input: 
    {
        "API": "4.0",
        "action": "inventory_move",
        "data": [
            {
                "barcodeid": "6853296789574115",
                "room": "1"
            },
            {
                "barcodeid": "6853296789574152",
                "room": "1"
            }
        ]
    }

    Example Output:
    {
        "sessiontime": "1384476925",
        "success": "1",
        "transactionid": "3278"
    }
    Args:
        token: Authentication token
        move_info: List of dictionaries with "barcodeid" and "room"
    
    Returns:
        Response data or None if failed
    """
    if not validate_token(token):
        return None
    
    if not move_info:
        logger.error("Invalid move_info provided")
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    # Validate move_info structure
    for item in move_info:
        if not isinstance(item, dict) or "barcodeid" not in item or "room" not in item:
            logger.error("Invalid move_info structure - each item must have 'barcodeid' and 'room'")
            return None
    
    data = {
        "API": "4.0",
        "action": "inventory_move",
        "sessionid": token,
        "data": move_info,
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "sublot_move")
        
        if response_data and str(response_data.get("success")) == "1":
            logger.info("Successfully moved sublot(s)")
            return response_data
        else:
            logger.error(f"Sublot move failed: {response_data}")
            # Return the detailed error information for better user feedback
            return {
                'success': False,
                'error': response_data.get('error', 'Unknown BioTrack error'),
                'errorcode': response_data.get('errorcode', 'Unknown'),
                'details': response_data
            }
            
    except Exception as e:
        logger.error(f"Failed to post sublot move: {e}")
        return None


def post_sublot_bulk_create(
    token: str, 
    sublot_data: List[Dict[str, str]]
) -> Optional[List[str]]:
    """
    Create inventory sublots in bulk using the original working pattern.
    
    Args:
        token: Authentication token
        sublot_data: List of dictionaries with "barcodeid" and "remove_quantity"
    
    Returns:
        List of new barcode IDs or None if failed
    """
    if not validate_token(token):
        return None
    
    if not sublot_data:
        logger.error("Invalid sublot_data provided")
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    # Validate sublot_data structure
    for item in sublot_data:
        if not isinstance(item, dict) or "barcodeid" not in item or "remove_quantity" not in item:
            logger.error("Invalid sublot_data structure - each item must have 'barcodeid' and 'remove_quantity'")
            return None
    
    data = {
        "API": "4.0",
        "action": "inventory_split",
        "sessionid": token,
        "sublot_id": "bulk_create",
        "data": sublot_data,
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "sublot_bulk_create")
        
        if response_data and str(response_data.get("success")) == "1":
            sublot_ids = response_data.get("barcode_id", [])
            logger.info(f"Successfully created {len(sublot_ids)} sublots in bulk")
            return sublot_ids
        else:
            logger.error(f"Bulk sublot creation failed: {response_data}")
            # Return the detailed error information for better user feedback
            return {
                'success': False,
                'error': response_data.get('error', 'Unknown BioTrack error'),
                'errorcode': response_data.get('errorcode', 'Unknown'),
                'details': response_data
            }
            
    except Exception as e:
        logger.error(f"Failed to create bulk sublots: {e}")
        return None


def post_manifest(
    token: str,
    manifest_info: Dict[str, Any],
    drivers: Union[str, List[str]],
    vehicle: str,
    location: str = "ACFB0000681"
) -> Optional[Dict[str, Any]]:
    """
    Create inventory manifest in BioTrack.

    Description: The inventory_manifest function will notify the traceability system of intent to transfer an inventory item. 
    This function will need to be called in instances of transfers from one license to another under the same ownership

    Example Input: 
    {
    "API": "4.0",
    "action": "inventory_manifest",
    "location": "12345",
    "stop_overview": {
        "approximate_departure": "1384476925",
        "approximate_arrival": "1384486925",
        "approximate_route": "Turn left on Main St.",
        "vendor_license": "25678787644",
        "stop_number": "1",
        "barcodeid": [
            "6853296789574115",
            "6853296789574116"
        ]
    },
    "employee_id": "23468",
    "employee_id_2": "23469",
    "vehicle_id": "2"
    }

    Example Output:
    {
        "sessiontime": "1384476925",
        "success": "1",
        "transactionid": "3278",
        "barcode_id": "6853296789574115" # this is the manifest id
    }

    Args:
        token: Authentication token
        manifest_info: Dictionary with manifest details including:
            - approximate_departure: Unix timestamp
            - approximate_arrival: Unix timestamp
            - approximate_route: Route description
            - stop_number: Always "1"
            - barcodeid: List of barcode IDs
            - vendor_license: Vendor license number
        drivers: Driver ID(s) - list of strings
        vehicle: Vehicle ID
        location: Location ID (default: "ACME0008473")
    
    Returns:
        Response data or None if failed
    """
    if not validate_token(token):
        return None
    
    if not manifest_info or not drivers or not vehicle:
        logger.error("Invalid manifest_info, drivers, or vehicle provided")
        return None
    
    # Import training mode function from app
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import get_training_mode
    
    training = get_training_mode()
    
    # Validate required manifest_info fields
    required_fields = ["approximate_departure", "approximate_arrival", "approximate_route", 
                      "stop_number", "barcodeid", "vendor_license"]
    for field in required_fields:
        if field not in manifest_info:
            logger.error(f"Missing required field in manifest_info: {field}")
            return None
    
    # Normalize drivers to list format
    if isinstance(drivers, str):
        drivers = [drivers]
    
    data = {
        "API": "4.0",
        "action": "inventory_manifest",
        "sessionid": token,
        "location": location,
        "stop_overview": manifest_info,
        "employee_id": drivers[0],
        "employee_id_2": drivers[1],
        "vehicle_id": vehicle,
        "training": training
    }
    
    try:
        response_data = _make_api_request(data, "manifest_creation")
        
        if response_data and str(response_data.get("success")) == "1":
            logger.info("Successfully created inventory manifest")
            return response_data.get("barcode_id")
        else:
            logger.error(f"Manifest creation failed: {response_data}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to post manifest: {e}")
        return None




