# Redis Worker Status Process - Complete Implementation Guide

This document explains how to implement a robust background job processing system with real-time status updates using Redis, RQ (Redis Queue), and a Flask web application. This pattern is perfect for long-running tasks like AI image generation, data processing, or any operation that needs to run in the background while providing real-time feedback to users.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Flask App     │    │   Redis + RQ    │
│   (Browser)     │    │   (API Server)  │    │   (Worker)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ 1. Submit Job         │                       │
         ├──────────────────────►│                       │
         │                       │ 2. Enqueue Job        │
         │                       ├──────────────────────►│
         │                       │                       │
         │ 3. Poll Status        │                       │
         ├──────────────────────►│                       │
         │                       │ 4. Check DB Status    │
         │                       │◄──────────────────────┤
         │ 5. Return Status      │                       │
         │◄──────────────────────┤                       │
         │                       │                       │
         │ 6. Job Complete       │                       │
         │◄──────────────────────┤                       │
```

## 📋 Prerequisites

- Python 3.8+
- Redis server
- Flask web framework
- RQ (Redis Queue) library

## 🚀 Setup Instructions

### 1. Install Dependencies

```bash
pip install redis rq flask python-dotenv
```

### 2. Redis Setup

**Local Development:**
```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

**Production (Docker):**
```yaml
# docker-compose.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

### 3. Environment Configuration

Create `.env` file:
```env
REDIS_URL=redis://localhost:6379/0
FLASK_ENV=development
```

## 🔧 Core Implementation

### 1. Task Queue Module (`utils/task_queue.py`)

```python
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

def get_character_queue():
    """Get character generation queue"""
    redis_conn = get_redis_connection()
    return Queue('character_generation', connection=redis_conn)

def enqueue_character_generation(character_id, reference_photo_path=None):
    """Enqueue character generation job with reference photo"""
    queue = get_character_queue()
    job = queue.enqueue(
        'utils.character_generation.generate_character_background_job',
        character_id,
        reference_photo_path,
        job_timeout='30m'  # 30 minute timeout for character generation
    )
    return job.id

def get_job_status(job_id):
    """Get job status"""
    queue = get_character_queue()
    job = queue.fetch_job(job_id)
    if job:
        return {
            'status': job.get_status(),
            'result': job.result,
            'error': str(job.exc_info) if job.exc_info else None
        }
    return None
```

### 2. Background Job Worker (`worker.py`)

```python
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
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_conn = Redis.from_url(redis_url)
    
    # Use SimpleWorker for Windows compatibility (no forking)
    worker = SimpleWorker(['character_generation', 'story_generation'], connection=redis_conn)
    
    # Clean up old failed jobs on startup
    print("Cleaning up old failed jobs...")
    try:
        from rq import Queue
        queue = Queue('character_generation', connection=redis_conn)
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
```

### 3. Background Job Function (`utils/character_generation.py`)

```python
"""
Character generation workflow module
Method-based approach for orchestrating character creation with Redis worker
"""

import time
from utils.database import execute_query

def generate_character_background_job(character_id, reference_photo_path=None):
    """RQ job function - generates character image in background"""
    try:
        print(f"=== RQ CHARACTER GENERATION STARTED ===")
        print(f"Character ID: {character_id}")
        print(f"Reference photo path: {reference_photo_path}")
        
        print(f"STEP 1: Getting character data...")
        character_data = _get_character_data(character_id)
        print(f"Character data retrieved: {type(character_data)}")
        
        print(f"STEP 2: Extracting character style...")
        style_preferences = _extract_character_style(character_data)
        print(f"Style preferences: {style_preferences}")
        
        print(f"STEP 3: Starting character image generation...")
        _update_character_status(character_id, 'generating', 'Generating character image...')
        
        # Simulate long-running process
        time.sleep(5)  # Replace with actual AI generation
        
        # Update status to completed
        _update_character_status(character_id, 'completed', 'Character generation completed')
        print(f"=== RQ CHARACTER GENERATION COMPLETED ===")
        
    except Exception as e:
        print(f"=== RQ CHARACTER GENERATION FAILED ===")
        _update_character_status(character_id, 'failed', f'Generation failed: {str(e)}')
        raise e

def _update_character_status(character_id, status, progress_message=None):
    """Helper - updates character generation status in database"""
    query = """
        INSERT INTO character_generations (character_id, status, progress_message, created_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (character_id) 
        DO UPDATE SET status = %s, progress_message = %s, updated_at = NOW()
    """
    
    execute_query(query, (character_id, status, progress_message, status, progress_message))
```

### 4. Database Model (`models.py`)

```python
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Character(db.Model):
    """Character model"""
    __tablename__ = 'characters'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    personality_profile = db.Column(db.String(50))
    art_style = db.Column(db.String(50))
    character_image_url = db.Column(db.Text)
    image_generation_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CharacterGeneration(db.Model):
    """Character generation tracking model"""
    __tablename__ = 'character_generations'
    
    character_id = db.Column(db.Integer, db.ForeignKey('characters.id'), primary_key=True)
    status = db.Column(db.String(20), default='pending')
    progress_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
```

### 5. Flask API Endpoints (`app.py`)

```python
from flask import Flask, request, jsonify
from utils.task_queue import enqueue_character_generation
from utils.character_generation import start_character_generation, get_character_generation_status

app = Flask(__name__)

@app.route('/api/characters', methods=['POST'])
def create_character():
    """Create a new character and start background generation"""
    try:
        data = request.get_json()
        
        # Create character in database
        character = Character(
            user_id=data['user_id'],
            name=data['name'],
            age=data['age'],
            gender=data['gender'],
            personality_profile=data.get('personality_profile'),
            art_style=data.get('art_style')
        )
        
        db.session.add(character)
        db.session.flush()  # Get the character ID
        
        # Start background generation
        start_character_generation(character.id, data.get('reference_photo_path'))
        
        return jsonify({
            "message": "Character created successfully",
            "character": {"id": character.id}
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to create character: {str(e)}"}), 500

@app.route('/api/characters/<int:character_id>/generation-status', methods=['GET'])
def get_character_generation_status_api(character_id):
    """Get character generation status"""
    try:
        status = get_character_generation_status(character_id)
        if not status:
            return jsonify({"error": "Character not found"}), 404
        
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": f"Failed to get character generation status: {str(e)}"}), 500
```

### 6. Status Tracking Function (`utils/character_generation.py`)

```python
def get_character_generation_status(character_id):
    """Get current generation status with progress calculation"""
    # Get character data from database
    character_query = """
        SELECT c.*, cg.status, cg.progress_message, cg.created_at as generation_started
        FROM characters c
        LEFT JOIN character_generations cg ON c.id = cg.character_id
        WHERE c.id = %s
    """
    
    character_result = execute_query(character_query, (character_id,))
    if not character_result:
        return None
    
    character_data = character_result[0]
    
    # Calculate status and progress
    status = character_data.get('status', 'pending')
    progress_message = character_data.get('progress_message', '')
    
    # Determine progress percentage based on status and time
    if status == 'completed':
        progress_percentage = 100
    elif status == 'failed':
        progress_percentage = 0
    elif status == 'generating':
        # Calculate progress based on time elapsed
        generation_started = character_data.get('generation_started')
        if generation_started:
            from datetime import datetime
            try:
                start_time = datetime.fromisoformat(str(generation_started).replace('Z', '+00:00'))
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                
                # Progress over time: 0-30 seconds = 10-50%, 30+ seconds = 50-90%
                if elapsed_seconds < 30:
                    progress_percentage = min(50, 10 + (elapsed_seconds / 30) * 40)
                else:
                    progress_percentage = min(90, 50 + ((elapsed_seconds - 30) / 60) * 40)
            except:
                progress_percentage = 50  # Fallback to 50% if time calculation fails
        else:
            progress_percentage = 25  # Just started
    else:
        progress_percentage = 0
    
    return {
        'character_id': character_data['id'],
        'generation_status': status,
        'progress_percentage': progress_percentage,
        'progress_message': progress_message,
        'created_at': character_data.get('created_at'),
        'generation_started': character_data.get('generation_started')
    }
```

## 🎨 Frontend Implementation

### 1. Progress Page Template (`templates/characters/generating.html`)

```html
{% extends "base.html" %}

{% block content %}
<div class="min-h-screen gradient-bg py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <!-- Generation Progress -->
        <div class="bg-white rounded-xl shadow-lg p-8 text-center">
            <div class="mb-8">
                <div class="animate-spin rounded-full h-20 w-20 border-b-4 border-character-primary mx-auto mb-6"></div>
                <h1 class="text-3xl font-bold text-character-text mb-4">Creating Your Character</h1>
                <p class="text-xl text-gray-600 mb-6" id="current-status">Preparing your character...</p>
            </div>
            
            <!-- Progress Bar -->
            <div class="mb-8">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-sm font-medium text-gray-700">Progress</span>
                    <span class="text-sm text-gray-500" id="progress-text">0%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-4">
                    <div class="bg-gradient-to-r from-story-primary to-story-accent h-4 rounded-full transition-all duration-1000" 
                         id="progress-bar" style="width: 0%"></div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const characterId = urlParams.get('character_id');
    
    if (!characterId) {
        window.location.href = '/characters';
        return;
    }
    
    let pollInterval;
    let isGenerating = true;
    
    // Start polling for character generation status
    startPolling();
    
    function startPolling() {
        pollInterval = setInterval(checkCharacterStatus, 3000); // Poll every 3 seconds
    }
    
    function checkCharacterStatus() {
        fetch(`/api/characters/${characterId}/generation-status`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error checking character status:', data.error);
                    return;
                }
                
                updateProgress(data);
                
                if (data.generation_status === 'completed') {
                    isGenerating = false;
                    clearInterval(pollInterval);
                    showCompletedState(data);
                } else if (data.generation_status === 'failed') {
                    isGenerating = false;
                    clearInterval(pollInterval);
                    showErrorState(data);
                }
            })
            .catch(error => {
                console.error('Error polling character status:', error);
            });
    }
    
    function updateProgress(data) {
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const currentStatus = document.getElementById('current-status');
        
        // Update progress bar
        progressBar.style.width = `${data.progress_percentage}%`;
        progressText.textContent = `${Math.round(data.progress_percentage)}%`;
        
        // Update status message
        if (data.progress_message) {
            currentStatus.textContent = data.progress_message;
        }
    }
    
    function showCompletedState(data) {
        document.querySelector('.animate-spin').classList.remove('animate-spin');
        document.querySelector('.animate-spin').classList.add('text-green-500');
        document.querySelector('.animate-spin').innerHTML = '✓';
        
        document.getElementById('current-status').textContent = 'Character generation completed!';
        
        // Redirect to character detail page after 2 seconds
        setTimeout(() => {
            window.location.href = `/characters/${characterId}`;
        }, 2000);
    }
    
    function showErrorState(data) {
        document.querySelector('.animate-spin').classList.remove('animate-spin');
        document.querySelector('.animate-spin').classList.add('text-red-500');
        document.querySelector('.animate-spin').innerHTML = '✗';
        
        document.getElementById('current-status').textContent = 'Character generation failed. Please try again.';
    }
});
</script>
{% endblock %}
```

## 🚀 Running the System

### 1. Start Redis Server
```bash
# Local development
redis-server

# Or with Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 2. Start the Worker Process
```bash
# In a separate terminal
python worker.py
```

### 3. Start the Flask Application
```bash
# In another terminal
python app.py
```

### 4. Access the Application
- Open browser to `http://localhost:5000`
- Create a character
- Watch the real-time progress updates

## 🔄 Complete Workflow

1. **User submits form** → Flask API receives request
2. **Character created** → Database record created
3. **Job enqueued** → Redis queue receives background job
4. **Worker processes** → Background worker picks up job
5. **Status updates** → Database updated with progress
6. **Frontend polls** → JavaScript polls status API every 3 seconds
7. **Real-time updates** → Progress bar and messages update
8. **Completion** → User redirected to results page

## 🛠️ Key Benefits

- **Non-blocking**: Long-running tasks don't freeze the UI
- **Real-time feedback**: Users see progress updates
- **Fault tolerance**: Failed jobs can be retried
- **Scalable**: Multiple workers can process jobs
- **Persistent**: Jobs survive server restarts
- **Monitoring**: Easy to track job status and failures

## 📊 Monitoring & Debugging

### Check Redis Queue Status
```bash
# Connect to Redis CLI
redis-cli

# List all queues
KEYS *

# Check queue length
LLEN rq:queue:character_generation

# View failed jobs
SMEMBERS rq:failed
```

### View Worker Logs
```bash
# Worker output shows job processing
python worker.py
```

### Database Status Check
```sql
-- Check character generation status
SELECT c.name, cg.status, cg.progress_message, cg.created_at
FROM characters c
LEFT JOIN character_generations cg ON c.id = cg.character_id
ORDER BY c.created_at DESC;
```

This implementation provides a robust, scalable background job processing system with real-time status updates that can be easily adapted to any Flask application requiring long-running tasks.
