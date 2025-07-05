#!/usr/bin/env python3
"""
Job Queue Service

Main service for managing job queue in YouTube Downloader.
Provides creation, scheduling, execution and monitoring of jobs.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
import json
import queue
import traceback

from .job_types import (
    Job, JobType, JobStatus, JobPriority, JobData, JobWorker, JobFailureType,
    create_job_with_defaults
)

# Database functions for settings
from database import get_user_setting

# Performance monitoring and optimization (Phase 7)
try:
    from utils.performance_monitor import get_performance_monitor
    from utils.database_optimizer import get_database_optimizer
    PHASE_7_ENABLED = True
except ImportError:
    PHASE_7_ENABLED = False


class JobQueueService:
    """Main job queue management service."""
    
    def __init__(self, db_path: str = None, max_workers: int = 1):
        # Database setup
        if db_path is None:
            # Use .env file to determine database path
            project_root = Path(__file__).parent.parent
            env_path = project_root / '.env'
            
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip().lstrip('\ufeff')
                            if line.startswith('DB_PATH='):
                                db_path = line.split('=', 1)[1].strip()
                                break
                except Exception:
                    pass
            
            if not db_path:
                db_path = str(project_root / 'tracks.db')
        
        self.db_path = db_path
        self.max_workers = max_workers
        
        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_threads: List[threading.Thread] = []
        
        # Worker management
        self._workers: Dict[str, JobWorker] = {}
        self._worker_queue = queue.Queue()
        
        # Job monitoring
        self._running_jobs: Dict[int, Job] = {}
        self._job_callbacks: Dict[int, List[Callable]] = {}
        
        # Statistics
        self._stats = {
            'total_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0,
            'start_time': datetime.utcnow()
        }
        
        # Phase 7: Performance monitoring and database optimization
        self._performance_monitor = None
        self._database_optimizer = None
        if PHASE_7_ENABLED:
            try:
                self._performance_monitor = get_performance_monitor(self.db_path, self)
                self._database_optimizer = get_database_optimizer(self.db_path, pool_size=15)
                print("✅ Phase 7 Performance & Optimization enabled")
            except Exception as e:
                print(f"⚠️ Phase 7 initialization failed: {e}")
        
        # Initialization
        self._init_database()
        self._start_worker_threads()
    
    def _init_database(self):
        """Initialize database for job queue operations."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if job_queue table exists
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='job_queue'
            """)
            
            if not cursor.fetchone():
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE job_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT NOT NULL,
                        job_data TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        priority INTEGER NOT NULL DEFAULT 5,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        log_file_path TEXT,
                        error_message TEXT,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        worker_id TEXT,
                        timeout_seconds INTEGER,
                        parent_job_id INTEGER,
                        FOREIGN KEY (parent_job_id) REFERENCES job_queue(id)
                    )
                """)
                
                # Create indexes for performance
                cursor.execute("CREATE INDEX idx_job_queue_status ON job_queue(status)")
                cursor.execute("CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC)")
                cursor.execute("CREATE INDEX idx_job_queue_created_at ON job_queue(created_at)")
                cursor.execute("CREATE INDEX idx_job_queue_type ON job_queue(job_type)")
                
                conn.commit()
    
    def _start_worker_threads(self):
        """Start worker threads."""
        for i in range(self.max_workers):
            worker_thread = threading.Thread(
                target=self._worker_loop,
                name=f"JobWorker-{i+1}",
                daemon=True
            )
            worker_thread.start()
            self._worker_threads.append(worker_thread)
    
    def _worker_loop(self):
        """Main worker thread loop with zombie detection."""
        worker_name = threading.current_thread().name
        last_zombie_check = time.time()
        zombie_check_interval = 300  # Check for zombies every 5 minutes
        
        while not self._stop_event.is_set():
            try:
                # Periodic zombie job check
                current_time = time.time()
                if current_time - last_zombie_check > zombie_check_interval:
                    self._cleanup_zombie_jobs()
                    last_zombie_check = current_time
                
                # Get next job from queue
                job = self._get_next_job()
                
                if job is None:
                    # No jobs available, wait a bit
                    time.sleep(1)
                    continue
                
                # Execute the job
                self._execute_job(job, worker_name)
                
            except Exception as e:
                print(f"Worker {worker_name} error: {e}")
                traceback.print_exc()
                time.sleep(5)  # Pause on error
    
    def _get_next_job(self) -> Optional[Job]:
        """Get next job for execution."""
        with self._lock:
            # Use optimized database connection if available
            if self._database_optimizer:
                with self._database_optimizer.get_optimized_connection() as conn:
                    return self._get_next_job_from_connection(conn)
            else:
                with sqlite3.connect(self.db_path) as conn:
                    return self._get_next_job_from_connection(conn)
    
    def _get_next_job_from_connection(self, conn) -> Optional[Job]:
        """Helper method to get next job from provided connection."""
        cursor = conn.cursor()
        
        # Look for jobs ready for execution considering retry timing
        current_time = datetime.utcnow().isoformat()
        cursor.execute("""
            SELECT id, job_type, job_data, status, priority, created_at,
                   log_file_path, error_message, retry_count, max_retries,
                   timeout_seconds, parent_job_id, next_retry_at, failure_type
            FROM job_queue 
            WHERE (
                status = 'pending' OR 
                (status = 'retrying' AND (next_retry_at IS NULL OR next_retry_at <= ?))
            )
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """, (current_time,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Create Job object
        job = Job(
            job_type=JobType(row[1]),
            job_data=JobData.from_json(row[2]),
            priority=JobPriority(row[4])
        )
        
        job.id = row[0]
        job.status = JobStatus(row[3])
        job.created_at = datetime.fromisoformat(row[5])
        job.log_file_path = row[6]
        job.error_message = row[7]
        job.retry_count = row[8]
        job.max_retries = row[9]
        job.timeout_seconds = row[10]
        job.parent_job_id = row[11]
        
        # New fields for enhanced error handling
        if row[12]:  # next_retry_at
            job.next_retry_at = datetime.fromisoformat(row[12])
        if row[13]:  # failure_type
            job.failure_type = JobFailureType(row[13])
        
        # Mark job as running
        cursor.execute("""
            UPDATE job_queue 
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (job.id,))
        conn.commit()
        
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        
        return job
    
    def _execute_job(self, job: Job, worker_name: str):
        """Execute a job."""
        job.worker_id = worker_name
        
        # Apply job execution delay (Phase 2: Job Queue Delay System)
        self._apply_job_delay(job)
        
        success = False
        error_message = None
        
        try:
            with self._lock:
                self._running_jobs[job.id] = job
            
            # Find suitable worker
            worker = self._find_worker_for_job(job)
            
            if worker is None:
                raise Exception(f"No worker available for job type {job.job_type.value}")
            
            # Execute job with built-in logging
            success = worker.execute_job_with_logging(job)
                
        except Exception as e:
            success = False
            error_message = str(e)
            # If job has logger, use it, otherwise print to console
            if job.get_logger():
                job.log_exception(e, "job execution in JobQueueService")
            else:
                print(f"Job {job.id} execution error: {e}")
                
        finally:
            # Update status in database
            with self._lock:
                if job.id in self._running_jobs:
                    del self._running_jobs[job.id]
                
                self._update_job_completion(job, success, error_message)
            
            # Call callbacks
            self._call_job_callbacks(job.id, success, error_message)
    
    def _apply_job_delay(self, job: Job):
        """Apply configured delay before job execution to prevent rate limiting."""
        try:
            # Get delay setting from database
            with sqlite3.connect(self.db_path) as conn:
                delay_seconds = int(get_user_setting(conn, 'job_execution_delay_seconds', '0'))
            
            if delay_seconds > 0:
                # Log the delay application
                worker_name = threading.current_thread().name
                from utils.logging_utils import log_message
                log_message(f"Applying job delay: {delay_seconds}s before executing job {job.id} (type: {job.job_type.value}) on worker {worker_name}")
                
                # Apply the delay
                time.sleep(delay_seconds)
                
        except Exception as e:
            # If there's an error getting/applying delay, log it but don't fail the job
            print(f"Warning: Failed to apply job delay for job {job.id}: {e}")
            # Continue without delay
    
    def _find_worker_for_job(self, job: Job) -> Optional[JobWorker]:
        """Find worker capable of executing the job."""
        for worker in self._workers.values():
            if worker.can_handle_job(job):
                return worker
        return None
    
    def _update_job_completion(self, job: Job, success: bool, error_message: Optional[str]):
        """Update completed job status with enhanced retry logic."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if success:
                new_status = JobStatus.COMPLETED
                self._stats['completed_jobs'] += 1
                
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                        log_file_path = ?
                    WHERE id = ?
                """, (new_status.value, job.log_file_path, job.id))
                
            else:
                # Enhanced retry logic with exponential backoff
                if job.can_retry():
                    # Schedule retry with exponential backoff
                    if job.schedule_retry():
                        new_status = JobStatus.RETRYING
                        
                        cursor.execute("""
                            UPDATE job_queue 
                            SET status = ?, retry_count = ?, error_message = ?, 
                                failure_type = ?, next_retry_at = ?, log_file_path = ?
                            WHERE id = ?
                        """, (
                            new_status.value, 
                            job.retry_count, 
                            error_message,
                            job.failure_type.value if job.failure_type else None,
                            job.next_retry_at.isoformat() if job.next_retry_at else None,
                            job.log_file_path,
                            job.id
                        ))
                    else:
                        # If schedule_retry returned False, move to dead letter
                        job.move_to_dead_letter("Failed to schedule retry")
                        new_status = JobStatus.DEAD_LETTER
                        self._stats['failed_jobs'] += 1
                        
                        cursor.execute("""
                            UPDATE job_queue 
                            SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                                error_message = ?, failure_type = ?, log_file_path = ?,
                                dead_letter_reason = ?, moved_to_dead_letter_at = ?
                            WHERE id = ?
                        """, (
                            new_status.value, 
                            error_message, 
                            job.failure_type.value if job.failure_type else None,
                            job.log_file_path,
                            job.dead_letter_reason,
                            job.moved_to_dead_letter_at.isoformat() if job.moved_to_dead_letter_at else None,
                            job.id
                        ))
                else:
                    # Maximum retry attempts exhausted
                    if job.retry_count >= job.max_retries:
                        job.move_to_dead_letter(f"Max retries ({job.max_retries}) exceeded")
                        new_status = JobStatus.DEAD_LETTER
                    else:
                        new_status = JobStatus.FAILED
                    
                    self._stats['failed_jobs'] += 1
                    
                    cursor.execute("""
                        UPDATE job_queue 
                        SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                            error_message = ?, failure_type = ?, log_file_path = ?,
                            dead_letter_reason = ?, moved_to_dead_letter_at = ?
                        WHERE id = ?
                    """, (
                        new_status.value, 
                        error_message, 
                        job.failure_type.value if job.failure_type else None,
                        job.log_file_path,
                        job.dead_letter_reason,
                        job.moved_to_dead_letter_at.isoformat() if job.moved_to_dead_letter_at else None,
                        job.id
                    ))
            
            conn.commit()
            job.status = new_status
    
    def _call_job_callbacks(self, job_id: int, success: bool, error_message: Optional[str]):
        """Call registered callbacks for the job."""
        callbacks = self._job_callbacks.get(job_id, [])
        
        for callback in callbacks:
            try:
                callback(job_id, success, error_message)
            except Exception as e:
                print(f"Callback error for job {job_id}: {e}")
        
        # Clear callbacks after execution
        if job_id in self._job_callbacks:
            del self._job_callbacks[job_id]
    
    def _cleanup_zombie_jobs(self):
        """Clean up zombie jobs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Find all running jobs
            cursor.execute("""
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, log_file_path, error_message, retry_count, 
                       max_retries, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue 
                WHERE status = 'running'
            """)
            
            zombie_count = 0
            for row in cursor.fetchall():
                job = Job(
                    job_type=JobType(row[1]),
                    job_data=JobData.from_json(row[2]),
                    priority=JobPriority(row[4])
                )
                
                job.id = row[0]
                job.status = JobStatus(row[3])
                job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
                job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
                job.log_file_path = row[7]
                job.error_message = row[8]
                job.retry_count = row[9]
                job.max_retries = row[10]
                job.timeout_seconds = row[11]
                job.parent_job_id = row[12]
                
                # New fields Phase 6
                if row[13]:  # failure_type
                    job.failure_type = JobFailureType(row[13])
                if row[14]:  # next_retry_at
                    job.next_retry_at = datetime.fromisoformat(row[14])
                job.dead_letter_reason = row[15]  # dead_letter_reason
                if row[16]:  # moved_to_dead_letter_at
                    job.moved_to_dead_letter_at = datetime.fromisoformat(row[16])
                
                # Check if job is zombie
                if job.is_zombie():
                    job.mark_as_zombie(f"Zombie detected during cleanup after {job.get_elapsed_time():.0f}s")
                    
                    # Update in database
                    cursor.execute("""
                        UPDATE job_queue 
                        SET status = ?, error_message = ?, failure_type = ?
                        WHERE id = ?
                    """, (
                        JobStatus.ZOMBIE.value,
                        job.error_message,
                        JobFailureType.TIMEOUT_ERROR.value,
                        job.id
                    ))
                    
                    zombie_count += 1
            
            if zombie_count > 0:
                conn.commit()
                print(f"Marked {zombie_count} zombie jobs during cleanup")
    
    def force_kill_zombie_jobs(self):
        """Forcefully terminate all zombie jobs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Find all zombie jobs
            cursor.execute("""
                SELECT id FROM job_queue WHERE status = 'zombie'
            """)
            
            zombie_ids = [row[0] for row in cursor.fetchall()]
            
            if zombie_ids:
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Zombie job forcefully terminated'
                    WHERE status = 'zombie'
                """)
                
                conn.commit()
                print(f"Force killed {len(zombie_ids)} zombie jobs")
                return len(zombie_ids)
            
            return 0
    
    # Public API methods
    
    def register_worker(self, worker: JobWorker):
        """Register worker for job execution."""
        with self._lock:
            self._workers[worker.worker_id] = worker
    
    def unregister_worker(self, worker_id: str):
        """Remove worker from system."""
        with self._lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
    
    def add_job(self, job: Job, callback: Optional[Callable] = None) -> int:
        """
        Add job to queue.
        
        Returns:
            ID of created job
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO job_queue (
                    job_type, job_data, status, priority, 
                    max_retries, timeout_seconds, parent_job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_type.value,
                job.job_data.to_json(),
                job.status.value,
                job.priority.value,
                job.max_retries,
                job.timeout_seconds,
                job.parent_job_id
            ))
            
            job_id = cursor.lastrowid
            conn.commit()
            
            job.id = job_id
            
            # Register callback if provided
            if callback:
                with self._lock:
                    if job_id not in self._job_callbacks:
                        self._job_callbacks[job_id] = []
                    self._job_callbacks[job_id].append(callback)
            
            self._stats['total_jobs'] += 1
            
            return job_id
    
    def create_and_add_job(self, job_type: JobType, callback: Optional[Callable] = None, **kwargs) -> int:
        """Create and add job with default settings."""
        job = create_job_with_defaults(job_type, **kwargs)
        return self.add_job(job, callback)
    
    def get_job(self, job_id: int) -> Optional[Job]:
        """Get job information."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, completed_at, log_file_path, error_message,
                       retry_count, max_retries, worker_id, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue WHERE id = ?
            """, (job_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job = Job(
                job_type=JobType(row[1]),
                job_data=JobData.from_json(row[2]),
                priority=JobPriority(row[4])
            )
            
            job.id = row[0]
            job.status = JobStatus(row[3])
            job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
            job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
            job.completed_at = datetime.fromisoformat(row[7]) if row[7] else None
            job.log_file_path = row[8]
            job.error_message = row[9]
            job.retry_count = row[10]
            job.max_retries = row[11]
            job.worker_id = row[12]
            job.timeout_seconds = row[13]
            job.parent_job_id = row[14]
            
            # New fields Phase 6
            if row[15]:  # failure_type
                job.failure_type = JobFailureType(row[15])
            if row[16]:  # next_retry_at
                job.next_retry_at = datetime.fromisoformat(row[16])
            job.dead_letter_reason = row[17]  # dead_letter_reason
            if row[18]:  # moved_to_dead_letter_at
                job.moved_to_dead_letter_at = datetime.fromisoformat(row[18])
            
            return job
    
    def get_jobs(self, status: Optional[JobStatus] = None, job_type: Optional[JobType] = None, 
                 limit: int = 100, offset: int = 0) -> List[Job]:
        """Get list of jobs with filtering."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, job_type, job_data, status, priority, created_at,
                       started_at, completed_at, log_file_path, error_message,
                       retry_count, max_retries, worker_id, timeout_seconds, parent_job_id,
                       failure_type, next_retry_at, dead_letter_reason, moved_to_dead_letter_at
                FROM job_queue
            """
            params = []
            conditions = []
            
            if status:
                conditions.append("status = ?")
                params.append(status.value)
            
            if job_type:
                conditions.append("job_type = ?")
                params.append(job_type.value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset)
            
            cursor.execute(query, params)
            
            jobs = []
            for row in cursor.fetchall():
                job = Job(
                    job_type=JobType(row[1]),
                    job_data=JobData.from_json(row[2]),
                    priority=JobPriority(row[4])
                )
                
                job.id = row[0]
                job.status = JobStatus(row[3])
                job.created_at = datetime.fromisoformat(row[5]) if row[5] else None
                job.started_at = datetime.fromisoformat(row[6]) if row[6] else None
                job.completed_at = datetime.fromisoformat(row[7]) if row[7] else None
                job.log_file_path = row[8]
                job.error_message = row[9]
                job.retry_count = row[10]
                job.max_retries = row[11]
                job.worker_id = row[12]
                job.timeout_seconds = row[13]
                job.parent_job_id = row[14]
                
                # New fields Phase 6
                if row[15]:  # failure_type
                    job.failure_type = JobFailureType(row[15])
                if row[16]:  # next_retry_at
                    job.next_retry_at = datetime.fromisoformat(row[16])
                job.dead_letter_reason = row[17]  # dead_letter_reason
                if row[18]:  # moved_to_dead_letter_at
                    job.moved_to_dead_letter_at = datetime.fromisoformat(row[18])
                
                jobs.append(job)
            
            return jobs
    
    def get_jobs_count(self, status: Optional[JobStatus] = None, job_type: Optional[JobType] = None) -> int:
        """Get jobs count with filtering without loading the actual job records."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) FROM job_queue"
            params = []
            conditions = []
            
            if status:
                conditions.append("status = ?")
                params.append(status.value)
            
            if job_type:
                conditions.append("job_type = ?")
                params.append(job_type.value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]
    
    def cancel_job(self, job_id: int) -> tuple[bool, str]:
        """Cancel a job. Returns (success, message)."""
        with self._lock:
            # First get job information
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, status, job_type, worker_id, started_at
                    FROM job_queue 
                    WHERE id = ?
                """, (job_id,))
                
                row = cursor.fetchone()
                if not row:
                    return False, "Job not found"
                
                job_id_db, status, job_type, worker_id, started_at = row
            
            # Check if job can be cancelled based on status
            if status in ['completed', 'cancelled']:
                return False, f"Job is already {status}"
            
            if status == 'failed':
                return False, "Job has already failed"
            
            if status == 'timeout':
                return False, "Job has already timed out"
            
            # Handle running jobs
            if status == 'running':
                # Check if job is in active jobs list
                if job_id in self._running_jobs:
                    # Try to cancel running job
                    job = self._running_jobs[job_id]
                    if hasattr(job, 'request_cancellation'):
                        # If job supports graceful cancellation
                        job.request_cancellation()
                        return True, "Cancellation request sent to running job"
                    else:
                        # Mark job as forcefully cancelled
                        job.status = JobStatus.CANCELLED
                        job.error_message = "Cancelled by user while running"
                        job.completed_at = datetime.utcnow()
                        
                        # Update in database
                        with sqlite3.connect(self.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE job_queue 
                                SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP,
                                    error_message = 'Cancelled by user while running'
                                WHERE id = ?
                            """, (job_id,))
                            conn.commit()
                        
                        # Remove from running jobs list
                        del self._running_jobs[job_id]
                        return True, "Running job cancelled (forced)"
                else:
                    # Job marked as running in DB but not found in active jobs
                    # This can happen after service restart
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE job_queue 
                            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP,
                                error_message = 'Cancelled by user (orphaned running job)'
                            WHERE id = ?
                        """, (job_id,))
                        conn.commit()
                    
                    return True, "Orphaned running job cancelled"
            
            # Cancel queued jobs (pending, retrying)
            if status in ['pending', 'retrying']:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE job_queue 
                        SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP,
                            error_message = 'Cancelled by user'
                        WHERE id = ? AND status IN ('pending', 'retrying')
                    """, (job_id,))
                    conn.commit()
                    
                    if cursor.rowcount > 0:
                        return True, "Job cancelled successfully"
                    else:
                        return False, "Job could not be cancelled (status may have changed)"
            
            # Unknown status
            return False, f"Cannot cancel job with status '{status}'"
    
    def retry_job(self, job_id: int) -> bool:
        """Retry a failed job."""
        with self._lock:
            # Check if job is currently running
            if job_id in self._running_jobs:
                return False
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check job status
                cursor.execute("""
                    SELECT status, retry_count, max_retries
                    FROM job_queue 
                    WHERE id = ?
                """, (job_id,))
                
                row = cursor.fetchone()
                if not row:
                    return False
                
                status, retry_count, max_retries = row
                
                # Check if job can be retried
                if status not in ['failed', 'cancelled', 'timeout']:
                    return False
                
                # Can also check retry limit (optional)
                # if retry_count >= max_retries:
                #     return False
                
                # Reset job for re-execution
                cursor.execute("""
                    UPDATE job_queue 
                    SET status = 'pending',
                        started_at = NULL,
                        completed_at = NULL,
                        worker_id = NULL,
                        error_message = NULL,
                        failure_type = NULL,
                        next_retry_at = NULL
                    WHERE id = ?
                """, (job_id,))
                
                conn.commit()
                
                return cursor.rowcount > 0
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            # Step 1: Direct DB connection (same as debug_stats)
            status_counts = {}
            type_counts = {}
            total_jobs = 0
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Count jobs by status
                    cursor.execute("SELECT status, COUNT(*) FROM job_queue GROUP BY status")
                    status_counts = dict(cursor.fetchall())
                    
                    # Count jobs by type
                    cursor.execute("SELECT job_type, COUNT(*) FROM job_queue GROUP BY job_type")
                    type_counts = dict(cursor.fetchall())
                    
                    # Total count
                    cursor.execute("SELECT COUNT(*) FROM job_queue")
                    total_jobs = cursor.fetchone()[0]
                    
            except Exception as e:
                # If DB access fails, return empty stats
                return {
                    'status_counts': {},
                    'type_counts': {},
                    'workers': {'total': 0, 'busy': 0, 'idle': 0, 'info': []},
                    'running_jobs': 0,
                    'total_jobs': 0,
                    'completed_jobs': 0,
                    'failed_jobs': 0,
                    'pending_jobs': 0,
                    'uptime_seconds': 0
                }
            
            # Step 2: Worker info
            try:
                with self._lock:
                    worker_info = [worker.get_worker_info() for worker in self._workers.values()]
                    running_jobs_count = len(self._running_jobs)
            except Exception as e:
                worker_info = []
                running_jobs_count = 0
                
            # Step 3: Stats calculation
            completed_jobs = status_counts.get('completed', 0)
            failed_jobs = status_counts.get('failed', 0)
            pending_jobs = status_counts.get('pending', 0)
            
            # Step 4: Uptime calculation
            try:
                start_time = self._stats.get('start_time', datetime.utcnow())
                if isinstance(start_time, str):
                    try:
                        start_time = datetime.fromisoformat(start_time.replace('GMT', '+00:00'))
                    except Exception:
                        start_time = datetime.utcnow()
                
                uptime = (datetime.utcnow() - start_time).total_seconds()
            except Exception as e:
                uptime = 0
            
            return {
                'status_counts': status_counts,
                'type_counts': type_counts,
                'workers': {
                    'total': len(self._workers),
                    'busy': sum(1 for w in worker_info if w.get('status') == 'busy'),
                    'idle': sum(1 for w in worker_info if w.get('status') == 'idle'),
                    'info': worker_info
                },
                'running_jobs': running_jobs_count,
                'total_jobs': total_jobs,
                'completed_jobs': completed_jobs,
                'failed_jobs': failed_jobs,
                'pending_jobs': pending_jobs,
                'uptime_seconds': uptime
            }
            
        except Exception as e:
            # Return basic statistics in case of error
            return {
                'status_counts': {},
                'type_counts': {},
                'workers': {
                    'total': 0,
                    'busy': 0,
                    'idle': 0,
                    'info': []
                },
                'running_jobs': 0,
                'total_jobs': 0,
                'completed_jobs': 0,
                'failed_jobs': 0,
                'pending_jobs': 0,
                'uptime_seconds': 0
            }
    
    def start(self):
        """Start service (if not already started)."""
        if not self._worker_threads or all(not t.is_alive() for t in self._worker_threads):
            print("Starting Job Queue Service workers...")
            self._stop_event.clear()
            self._worker_threads.clear()
            self._start_worker_threads()
            print(f"Job Queue Service started with {len(self._worker_threads)} workers")
    
    def stop(self):
        """Stop service (alias for shutdown)."""
        self.shutdown()
    
    def shutdown(self, graceful_timeout: int = 30):
        """Graceful shutdown of service with waiting for current jobs to complete."""
        print("Initiating graceful shutdown of Job Queue Service...")
        
        # Check current running jobs
        running_jobs = list(self._running_jobs.values())
        if running_jobs:
            print(f"Waiting for {len(running_jobs)} running jobs to complete (timeout: {graceful_timeout}s)...")
            
            # Wait for current jobs to complete with timeout
            start_time = time.time()
            while running_jobs and (time.time() - start_time) < graceful_timeout:
                time.sleep(1)
                # Update active jobs list
                with self._lock:
                    running_jobs = list(self._running_jobs.values())
            
            # If there are unfinished jobs remaining, mark them as cancelled
            if running_jobs:
                print(f"Force cancelling {len(running_jobs)} remaining jobs...")
                for job in running_jobs:
                    job.status = JobStatus.CANCELLED
                    job.error_message = "Cancelled due to service shutdown"
                    job.completed_at = datetime.utcnow()
                    
                    # Update in database
                    try:
                        with sqlite3.connect(self.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE job_queue 
                                SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                                    error_message = ?
                                WHERE id = ?
                            """, (JobStatus.CANCELLED.value, job.error_message, job.id))
                            conn.commit()
                    except Exception as e:
                        print(f"Error updating cancelled job {job.id}: {e}")
        
        # Final zombie job cleanup
        print("Performing final zombie cleanup...")
        self._cleanup_zombie_jobs()
        
        # Signal threads to stop
        self._stop_event.set()
        
        # Wait for all worker threads to complete
        print("Stopping worker threads...")
        for thread in self._worker_threads:
            thread.join(timeout=10)  # Increased timeout for graceful shutdown
            if thread.is_alive():
                print(f"Warning: Worker thread {thread.name} did not shut down gracefully")
        
        # Clear data
        with self._lock:
            self._workers.clear()
            self._running_jobs.clear()
            self._job_callbacks.clear()
        
        print("Job Queue Service shut down gracefully")


# Singleton instance
_job_queue_service: Optional[JobQueueService] = None


def get_job_queue_service(db_path: str = None, max_workers: int = 1) -> JobQueueService:
    """Get singleton instance of job queue service."""
    global _job_queue_service
    
    if _job_queue_service is None:
        _job_queue_service = JobQueueService(db_path, max_workers)
    
    return _job_queue_service


def shutdown_job_queue_service():
    """Shutdown singleton service."""
    global _job_queue_service
    
    if _job_queue_service is not None:
        _job_queue_service.shutdown()
        _job_queue_service = None 