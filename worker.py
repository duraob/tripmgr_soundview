#!/usr/bin/env python3
"""
RQ Worker for background job processing
Run this in a separate terminal to process background jobs
"""

import os
import sys
from rq import Worker
from rq.worker import SimpleWorker
from redis import Redis
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

def start_worker():
    """Start RQ worker for background processing"""
    # Import Flask app to ensure proper context
    from app import app
    
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_conn = Redis.from_url(redis_url)
    
    # Use SimpleWorker for Windows compatibility (no forking)
    worker = SimpleWorker(['trip_execution'], connection=redis_conn)
    
    # Clean up old failed jobs on startup
    print("Cleaning up old failed jobs...")
    try:
        from rq import Queue
        queue = Queue('trip_execution', connection=redis_conn)
        failed_count = len(queue.failed_job_registry)
        if failed_count > 0:
            for job_id in list(queue.failed_job_registry.get_job_ids()):
                queue.failed_job_registry.remove(job_id)
            print(f"Cleared {failed_count} old failed jobs")
        else:
            print("No old failed jobs to clean")
    except Exception as e:
        print(f"Warning: Could not clean old jobs: {e}")
    
    print("Starting RQ worker for background processing...")
    print("Press Ctrl+C to stop the worker")
    worker.work()

if __name__ == "__main__":
    start_worker()
