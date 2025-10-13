"""
Timezone utility functions for US Eastern Standard Time (EST) with DST handling
"""

from datetime import datetime, timezone, timedelta
import zoneinfo

# US Eastern timezone with automatic DST handling
US_EASTERN_TZ = zoneinfo.ZoneInfo("America/New_York")

# Legacy US Eastern Standard Time (UTC-5) - kept for backward compatibility
US_EASTERN = timezone(timedelta(hours=-5))

def get_est_now():
    """Get current time in EST/EDT with DST handling"""
    return datetime.now(US_EASTERN_TZ)

def convert_utc_to_est(utc_dt):
    """Convert UTC datetime to EST/EDT with DST handling"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(US_EASTERN_TZ)

def convert_est_to_utc(est_dt):
    """Convert EST/EDT datetime to UTC with DST handling"""
    if est_dt.tzinfo is None:
        est_dt = est_dt.replace(tzinfo=US_EASTERN_TZ)
    return est_dt.astimezone(timezone.utc)

def format_est_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Format datetime in EST/EDT with DST handling"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=US_EASTERN_TZ)
    return dt.strftime(format_str)

def create_est_datetime_with_dst(date_obj, time_str):
    """
    Create timezone-aware datetime that respects DST transitions.
    
    Args:
        date_obj: date object (from datetime.date)
        time_str: time string in HH:MM format
        
    Returns:
        timezone-aware datetime in EST/EDT
    """
    # Parse time string
    time_parts = time_str.split(':')
    hour = int(time_parts[0])
    minute = int(time_parts[1])
    
    # Create naive datetime first
    naive_dt = datetime.combine(date_obj, datetime.min.time().replace(hour=hour, minute=minute))
    
    # Convert to timezone-aware datetime in Eastern timezone
    # This automatically handles DST transitions
    return naive_dt.replace(tzinfo=US_EASTERN_TZ)

def ensure_est_timezone(dt):
    """
    Ensure datetime is properly timezone-aware in EST/EDT.
    
    Args:
        dt: datetime object (may be naive or timezone-aware)
        
    Returns:
        timezone-aware datetime in EST/EDT
    """
    if dt.tzinfo is None:
        # Naive datetime - assume it's in Eastern time
        return dt.replace(tzinfo=US_EASTERN_TZ)
    else:
        # Already timezone-aware - convert to Eastern time
        return dt.astimezone(US_EASTERN_TZ)

