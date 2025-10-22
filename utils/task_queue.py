"""
Task queue management using Redis and RQ
Method-based module following coding protocol
"""

import os
from redis import Redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()

def get_redis_connection():
    """Get Redis connection"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    return Redis.from_url(redis_url)

def get_trip_queue():
    """Get trip execution queue"""
    redis_conn = get_redis_connection()
    return Queue('trip_execution', connection=redis_conn)

def enqueue_trip_execution(trip_id):
    """Enqueue trip execution job"""
    queue = get_trip_queue()
    job = queue.enqueue(
        'utils.trip_execution.execute_trip_background_job',
        trip_id,
        job_timeout='30m'  # 30 minute timeout for trip execution
    )
    return job.id

def get_job_status(job_id):
    """Get job status"""
    queue = get_trip_queue()
    job = queue.fetch_job(job_id)
    if job:
        return {
            'status': job.get_status(),
            'result': job.result,
            'error': str(job.exc_info) if job.exc_info else None
        }
    return None
