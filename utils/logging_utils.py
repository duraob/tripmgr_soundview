"""
Logging utilities for structured logging throughout the application.

Provides helper functions for adding structured data to log entries
and common logging patterns.
"""

import logging
from typing import Dict, Any, Optional


def log_with_context(logger: logging.Logger, level: int, message: str, 
                    context: Optional[Dict[str, Any]] = None, **kwargs):
    """
    Log a message with structured context data.
    
    Args:
        logger: Logger instance to use
        level: Log level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        context: Dictionary of context data to include
        **kwargs: Additional key-value pairs to include in context
    """
    extra_fields = context or {}
    extra_fields.update(kwargs)
    
    logger.log(level, message, extra={'extra_fields': extra_fields})


def log_user_action(logger: logging.Logger, action: str, user_id: Optional[int] = None, 
                   username: Optional[str] = None, **kwargs):
    """
    Log a user action with user context.
    
    Args:
        logger: Logger instance to use
        action: Description of the action performed
        user_id: User ID (if available)
        username: Username (if available)
        **kwargs: Additional context data
    """
    context = {
        'action_type': 'user_action',
        'action': action
    }
    
    if user_id is not None:
        context['user_id'] = user_id
    if username is not None:
        context['username'] = username
    
    context.update(kwargs)
    log_with_context(logger, logging.INFO, f"User action: {action}", context)


def log_api_call(logger: logging.Logger, api_name: str, endpoint: str, 
                status: str, duration_ms: Optional[float] = None, **kwargs):
    """
    Log an API call with performance and status information.
    
    Args:
        logger: Logger instance to use
        api_name: Name of the API (e.g., 'biotrack', 'leaftrade')
        endpoint: API endpoint called
        status: Call status ('success', 'error', 'timeout')
        duration_ms: Call duration in milliseconds
        **kwargs: Additional context data
    """
    context = {
        'action_type': 'api_call',
        'api_name': api_name,
        'endpoint': endpoint,
        'status': status
    }
    
    if duration_ms is not None:
        context['duration_ms'] = duration_ms
    
    context.update(kwargs)
    
    level = logging.ERROR if status == 'error' else logging.INFO
    log_with_context(logger, level, f"API call: {api_name} - {endpoint} - {status}", context)


def log_trip_event(logger: logging.Logger, trip_id: int, event: str, 
                  status: str, **kwargs):
    """
    Log a trip-related event.
    
    Args:
        logger: Logger instance to use
        trip_id: Trip ID
        event: Event type (e.g., 'created', 'executed', 'status_changed')
        status: Event status ('success', 'error', 'pending')
        **kwargs: Additional context data
    """
    context = {
        'action_type': 'trip_event',
        'trip_id': trip_id,
        'event': event,
        'status': status
    }
    context.update(kwargs)
    
    level = logging.ERROR if status == 'error' else logging.INFO
    log_with_context(logger, level, f"Trip event: {event} - Trip {trip_id} - {status}", context)
