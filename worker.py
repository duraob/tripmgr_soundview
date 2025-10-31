#!/usr/bin/env python3
"""
RQ Worker for background job processing
Run this in a separate terminal to process background jobs
Unified approach - works on both Windows and Ubuntu like trip execution
"""

import os
import sys
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
    
    # Clean up old failed jobs on startup
    print("Cleaning up old failed jobs...")
    try:
        from rq import Queue
        for queue_name in ['trip_execution', 'report_generation']:
            queue = Queue(queue_name, connection=redis_conn)
            failed_count = len(queue.failed_job_registry)
            if failed_count > 0:
                for job_id in list(queue.failed_job_registry.get_job_ids()):
                    queue.failed_job_registry.remove(job_id)
                print(f"Cleared {failed_count} old failed jobs from {queue_name}")
            else:
                print(f"No old failed jobs to clean from {queue_name}")
    except Exception as e:
        print(f"Warning: Could not clean old jobs: {e}")
    
    # Reset stuck report statuses in database (if no active jobs in queue)
    print("Checking for stuck report statuses...")
    try:
        from app import app
        with app.app_context():
            from rq import Queue
            from utils.rpt_generation import _get_report_status, _set_preference
            from models import db
            
            report_queue = Queue('report_generation', connection=redis_conn)
            queue_length = len(report_queue)
            
            # Only reset if queue is empty (no active job processing)
            if queue_length == 0:
                for report_type in ['inventory', 'finished_goods']:
                    status = _get_report_status(report_type)
                    if status == 'generating':
                        print(f"Resetting stuck '{report_type}' report status (queue is empty)")
                        _set_preference(f'{report_type}_status', 'none')
                        _set_preference(f'{report_type}_error', '')
                db.session.commit()
                print("Stuck status check complete")
            else:
                print(f"Queue has {queue_length} job(s), skipping status reset")
    except Exception as e:
        print(f"Warning: Could not check/reset stuck statuses: {e}")
    
    # Use SimpleWorker for both platforms (same as trip execution)
    # SimpleWorker handles cross-platform compatibility automatically
    worker = SimpleWorker(['trip_execution', 'report_generation'], connection=redis_conn)
    
    print("Starting RQ worker for background processing...")
    print("Press Ctrl+C to stop the worker")
    worker.work()

if __name__ == "__main__":
    start_worker()
