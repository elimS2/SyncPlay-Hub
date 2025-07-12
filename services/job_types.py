#!/usr/bin/env python3
"""
Job Types and Base Classes for Job Queue System

Defines job types and base architecture for job queue system.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import time
import random


# Delayed import to avoid circular dependencies
def _get_job_logger_class():
    """Lazy import of JobLogger to avoid circular dependencies."""
    try:
        from utils.job_logging import JobLogger
        return JobLogger
    except ImportError:
        return None


class JobType(Enum):
    """Job types in the queue system."""
    
    # Download tasks
    CHANNEL_DOWNLOAD = "channel_download"
    PLAYLIST_DOWNLOAD = "playlist_download" 
    SINGLE_VIDEO_DOWNLOAD = "single_video_download"
    
    # Metadata tasks
    METADATA_EXTRACTION = "metadata_extraction"
    CHANNEL_METADATA_UPDATE = "channel_metadata_update"
    PLAYLIST_METADATA_UPDATE = "playlist_metadata_update"
    SINGLE_VIDEO_METADATA_EXTRACTION = "single_video_metadata_extraction"  # Phase 3: Single video metadata extraction
    
    # Maintenance tasks
    FILE_CLEANUP = "file_cleanup"
    DATABASE_CLEANUP = "database_cleanup"
    LOG_CLEANUP = "log_cleanup"
    METADATA_CLEANUP = "metadata_cleanup"
    
    # Synchronization tasks
    CHANNEL_SYNC = "channel_sync"
    PLAYLIST_SYNC = "playlist_sync"
    LIBRARY_SCAN = "library_scan"
    QUICK_SYNC = "quick_sync"
    
    # System tasks
    DATABASE_BACKUP = "database_backup"
    SYSTEM_MAINTENANCE = "system_maintenance"


class JobStatus(Enum):
    """Job execution statuses."""
    
    PENDING = "pending"        # Waiting for execution
    RUNNING = "running"        # Currently executing
    COMPLETED = "completed"    # Successfully completed
    FAILED = "failed"          # Failed with error
    CANCELLED = "cancelled"    # Cancelled by user
    TIMEOUT = "timeout"        # Execution timeout exceeded
    RETRYING = "retrying"      # Waiting for retry
    DEAD_LETTER = "dead_letter"  # Moved to dead letter queue
    ZOMBIE = "zombie"          # Stuck task (requires forced termination)


class JobPriority(Enum):
    """Job priorities."""
    
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 15
    CRITICAL = 20


class JobFailureType(Enum):
    """Job failure types for determining retry strategy."""
    
    UNKNOWN = "unknown"                    # Unknown error
    NETWORK_ERROR = "network_error"        # Network error (retry with backoff)
    TIMEOUT_ERROR = "timeout_error"        # Execution timeout
    RESOURCE_ERROR = "resource_error"      # Resource shortage (memory, disk)
    PERMISSION_ERROR = "permission_error"  # Permission errors
    CONFIGURATION_ERROR = "config_error"   # Configuration errors (no retry)
    VALIDATION_ERROR = "validation_error"  # Data validation errors (no retry)
    SYSTEM_ERROR = "system_error"          # System errors
    WORKER_ERROR = "worker_error"          # Worker logic errors


class RetryConfig:
    """Retry mechanism configuration."""
    
    def __init__(
        self,
        initial_delay: float = 1.0,        # Initial delay in seconds
        max_delay: float = 300.0,          # Maximum delay (5 minutes)
        backoff_multiplier: float = 2.0,   # Multiplier for exponential backoff
        jitter: bool = True,               # Add random delay
        max_jitter: float = 0.1            # Maximum jitter (10% of delay)
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.max_jitter = max_jitter
    
    def calculate_delay(self, retry_count: int) -> float:
        """Calculates retry delay with exponential backoff."""
        if retry_count <= 0:
            return self.initial_delay
        
        # Exponential backoff
        delay = self.initial_delay * (self.backoff_multiplier ** (retry_count - 1))
        
        # Limit with maximum delay
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter and delay > 0:
            jitter_amount = delay * self.max_jitter
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)
    
    def get_next_retry_time(self, retry_count: int) -> datetime:
        """Returns next retry time."""
        delay = self.calculate_delay(retry_count)
        return datetime.utcnow() + timedelta(seconds=delay)


class JobData:
    """Container for job data with typing."""
    
    def __init__(self, **kwargs):
        self._data = kwargs
    
    def to_json(self) -> str:
        """Serialize to JSON for database storage."""
        return json.dumps(self._data, ensure_ascii=False, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'JobData':
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)
    
    def get(self, key: str, default=None):
        """Get value by key."""
        return self._data.get(key, default)
    
    def set(self, key: str, value):
        """Set value."""
        self._data[key] = value
    
    def __getitem__(self, key):
        return self._data[key]
    
    def __setitem__(self, key, value):
        self._data[key] = value
    
    def __contains__(self, key):
        return key in self._data
    
    def keys(self):
        return self._data.keys()
    
    def items(self):
        return self._data.items()
    
    def __repr__(self):
        return f"JobData({self._data})"


class Job:
    """Job representation in the queue system."""
    
    def __init__(
        self,
        job_type: JobType,
        job_data: JobData,
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: int = 3,
        timeout_seconds: Optional[int] = None,
        parent_job_id: Optional[int] = None
    ):
        # Basic fields
        self.id: Optional[int] = None
        self.job_type = job_type
        self.job_data = job_data
        self.status = JobStatus.PENDING
        self.priority = priority
        
        # Timestamps
        self.created_at: Optional[datetime] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Logging and errors
        self.log_file_path: Optional[str] = None
        self.error_message: Optional[str] = None
        self.failure_type: Optional[JobFailureType] = None
        self.last_error_traceback: Optional[str] = None
        
        # Retry logic
        self.retry_count: int = 0
        self.max_retries = max_retries
        self.next_retry_at: Optional[datetime] = None
        self.retry_config = RetryConfig()
        
        # Dead letter queue
        self.dead_letter_reason: Optional[str] = None
        self.moved_to_dead_letter_at: Optional[datetime] = None
        
        # Execution
        self.worker_id: Optional[str] = None
        self.timeout_seconds = timeout_seconds
        
        # Dependencies
        self.parent_job_id = parent_job_id
        
        # Job logger (created when starting execution)
        self._job_logger: Optional['JobLogger'] = None
    
    def create_logger(self) -> Optional['JobLogger']:
        """Creates job logger."""
        if self.id is None:
            return None
            
        JobLoggerClass = _get_job_logger_class()
        if JobLoggerClass is None:
            return None
            
        try:
            self._job_logger = JobLoggerClass(self.id, self.job_type.value)
            self.log_file_path = self._job_logger.get_log_files()['directory']
            return self._job_logger
        except Exception as e:
            print(f"Failed to create job logger for job {self.id}: {e}")
            return None
    
    def get_logger(self) -> Optional['JobLogger']:
        """Returns job logger."""
        return self._job_logger
    
    def log_info(self, message: str):
        """Logs informational message."""
        if self._job_logger:
            self._job_logger.info(message)
    
    def log_error(self, message: str):
        """Logs error."""
        if self._job_logger:
            self._job_logger.error(message)
    
    def log_progress(self, message: str, percentage: Optional[float] = None):
        """Logs execution progress."""
        if self._job_logger:
            self._job_logger.progress(message, percentage)
    
    def log_exception(self, exc: Exception, context: str = ""):
        """Logs exception."""
        if self._job_logger:
            self._job_logger.log_exception(exc, context)
    
    def finalize_logging(self, success: bool, error_message: Optional[str] = None):
        """Finalizes job logging."""
        if self._job_logger:
            self._job_logger.finalize(success, error_message)
            self._job_logger = None
    
    @classmethod
    def create(
        cls,
        job_type: JobType,
        priority: JobPriority = JobPriority.NORMAL,
        timeout_seconds: Optional[int] = None,
        parent_job_id: Optional[int] = None,
        **job_data_kwargs
    ) -> 'Job':
        """Convenient method for creating job."""
        job_data = JobData(**job_data_kwargs)
        return cls(
            job_type=job_type,
            job_data=job_data,
            priority=priority,
            timeout_seconds=timeout_seconds,
            parent_job_id=parent_job_id
        )
    
    def can_retry(self) -> bool:
        """Can job be retried."""
        # Do not retry job in dead letter queue or zombie
        if self.status in [JobStatus.DEAD_LETTER, JobStatus.ZOMBIE, JobStatus.CANCELLED]:
            return False
        
        # Check basic conditions
        if not (self.status in [JobStatus.FAILED, JobStatus.TIMEOUT] and 
                self.retry_count < self.max_retries):
            return False
        
        # Some failure types should not be retried
        non_retryable_failures = [
            JobFailureType.CONFIGURATION_ERROR,
            JobFailureType.VALIDATION_ERROR,
            JobFailureType.PERMISSION_ERROR
        ]
        
        if self.failure_type in non_retryable_failures:
            return False
        
        return True
    
    def is_ready_for_retry(self) -> bool:
        """Is job ready for retry (considering time)."""
        if not self.can_retry():
            return False
        
        if self.next_retry_at is None:
            return True
        
        return datetime.utcnow() >= self.next_retry_at
    
    def schedule_retry(self) -> bool:
        """Schedules next retry."""
        if not self.can_retry():
            return False
        
        self.retry_count += 1
        self.next_retry_at = self.retry_config.get_next_retry_time(self.retry_count)
        self.status = JobStatus.RETRYING
        
        self.log_info(f"Retry #{self.retry_count} scheduled for {self.next_retry_at.isoformat()}")
        return True
    
    def move_to_dead_letter(self, reason: str = None) -> bool:
        """Moves job to dead letter queue."""
        if self.status == JobStatus.DEAD_LETTER:
            return False
        
        self.status = JobStatus.DEAD_LETTER
        self.dead_letter_reason = reason or f"Max retries ({self.max_retries}) exceeded"
        self.moved_to_dead_letter_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        
        self.log_error(f"Job moved to dead letter queue: {self.dead_letter_reason}")
        return True
    
    def classify_failure(self, exception: Exception) -> JobFailureType:
        """Classifies failure for determining retry strategy."""
        import traceback
        
        # Save full traceback
        self.last_error_traceback = traceback.format_exc()
        
        # Failure classification by exception type
        exc_type = type(exception).__name__.lower()
        exc_message = str(exception).lower()
        
        # Network errors
        if any(keyword in exc_type for keyword in ['connection', 'network', 'timeout', 'socket']):
            return JobFailureType.NETWORK_ERROR
        
        if any(keyword in exc_message for keyword in ['connection', 'network', 'timeout']):
            return JobFailureType.NETWORK_ERROR
        
        # Resource errors
        if any(keyword in exc_type for keyword in ['memory', 'disk', 'space']):
            return JobFailureType.RESOURCE_ERROR
        
        if any(keyword in exc_message for keyword in ['no space', 'memory', 'disk full']):
            return JobFailureType.RESOURCE_ERROR
        
        # Permission errors
        if any(keyword in exc_type for keyword in ['permission', 'access', 'forbidden']):
            return JobFailureType.PERMISSION_ERROR
        
        # Validation errors
        if any(keyword in exc_type for keyword in ['validation', 'value', 'assertion']):
            return JobFailureType.VALIDATION_ERROR
        
        # Timeout errors - priority over network errors
        if exc_type == 'timeouterror' or ('timeout' in exc_type and 'error' in exc_type):
            return JobFailureType.TIMEOUT_ERROR
        
        # Default - unknown error
        return JobFailureType.UNKNOWN
    
    def should_timeout(self) -> bool:
        """Has execution timeout exceeded."""
        if not self.timeout_seconds or not self.started_at:
            return False
        
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        return elapsed > self.timeout_seconds
    
    def is_zombie(self, zombie_threshold_minutes: int = 60) -> bool:
        """Checks if job is zombie (stuck)."""
        if self.status != JobStatus.RUNNING:
            return False
        
        if not self.started_at:
            return False
        
        # Job is considered zombie if executing too long without updates
        elapsed_minutes = (datetime.utcnow() - self.started_at).total_seconds() / 60
        
        # If there's timeout, use it as basis for zombie detection
        if self.timeout_seconds:
            timeout_minutes = self.timeout_seconds / 60
            zombie_threshold = max(zombie_threshold_minutes, timeout_minutes * 2)
        else:
            zombie_threshold = zombie_threshold_minutes
        
        return elapsed_minutes > zombie_threshold
    
    def mark_as_zombie(self, reason: str = None):
        """Marks job as zombie."""
        if self.status == JobStatus.RUNNING:
            self.status = JobStatus.ZOMBIE
            self.error_message = reason or f"Task became zombie after {self.get_elapsed_time():.0f} seconds"
            self.failure_type = JobFailureType.TIMEOUT_ERROR
            
            self.log_error(f"Job marked as zombie: {self.error_message}")
    
    def force_kill(self, reason: str = None):
        """Forcibly terminates zombie job."""
        if self.status == JobStatus.ZOMBIE:
            self.status = JobStatus.FAILED
            self.completed_at = datetime.utcnow()
            self.error_message = reason or "Zombie job forcefully terminated"
            
            self.log_error(f"Zombie job killed: {self.error_message}")
    
    def get_elapsed_time(self) -> Optional[float]:
        """Execution time in seconds."""
        if not self.started_at:
            return None
        
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary for API."""
        return {
            'id': self.id,
            'job_type': self.job_type.value,
            'job_data': self.job_data._data,
            'status': self.status.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'log_file_path': self.log_file_path,
            'error_message': self.error_message,
            'failure_type': self.failure_type.value if self.failure_type else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'worker_id': self.worker_id,
            'timeout_seconds': self.timeout_seconds,
            'parent_job_id': self.parent_job_id,
            'elapsed_time': self.get_elapsed_time(),
            'dead_letter_reason': self.dead_letter_reason,
            'moved_to_dead_letter_at': self.moved_to_dead_letter_at.isoformat() if self.moved_to_dead_letter_at else None,
            'can_retry': self.can_retry(),
            'is_ready_for_retry': self.is_ready_for_retry(),
            'is_zombie': self.is_zombie()
        }
    
    def __repr__(self):
        return f"Job(id={self.id}, type={self.job_type.value}, status={self.status.value})"


class JobWorker(ABC):
    """Base class for job executors."""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.current_job: Optional[Job] = None
    
    @abstractmethod
    def get_supported_job_types(self) -> list[JobType]:
        """Returns list of supported job types."""
        pass
    
    def execute_job_with_logging(self, job: Job) -> bool:
        """
        Executes job with full logging and enhanced error handling.
        
        Args:
            job: Job to execute
            
        Returns:
            True if job executed successfully, False if failed
        """
        # Create job logger
        logger = job.create_logger()
        
        success = False
        error_message = None
        failure_type = None
        
        # Mark job start
        self.current_job = job
        
        try:
            job.log_info(f"Starting job execution with worker {self.worker_id}")
            job.log_info(f"Job data: {job.job_data._data}")
            job.log_info(f"Retry attempt: {job.retry_count + 1}/{job.max_retries + 1}")
            
            # Check timeout before execution
            if job.should_timeout():
                raise TimeoutError(f"Job timeout ({job.timeout_seconds}s) exceeded before execution")
            
            # Use output capture if logger is available
            if logger:
                with logger.capture_output():
                    success = self.execute_job(job)
            else:
                success = self.execute_job(job)
                
            if success:
                job.log_info("Job completed successfully")
            else:
                error_message = "Job execution returned False"
                failure_type = JobFailureType.WORKER_ERROR
                job.log_error(error_message)
                
        except TimeoutError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.TIMEOUT_ERROR
            job.log_exception(e, f"timeout in {self.worker_id}")
            
        except PermissionError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.PERMISSION_ERROR
            job.log_exception(e, f"permission error in {self.worker_id}")
            
        except ValueError as e:
            success = False
            error_message = str(e)
            failure_type = JobFailureType.VALIDATION_ERROR
            job.log_exception(e, f"validation error in {self.worker_id}")
            
        except Exception as e:
            success = False
            error_message = str(e)
            # Automatic failure classification
            failure_type = job.classify_failure(e)
            job.log_exception(e, f"execute_job in {self.worker_id}")
            
        finally:
            # Update error information
            if not success and error_message:
                job.error_message = error_message
                job.failure_type = failure_type
            
            # Clear current_job
            self.current_job = None
            
            # Finalize logging
            job.finalize_logging(success, error_message)
            
        return success

    @abstractmethod
    def execute_job(self, job: Job) -> bool:
        """
        Executes job.
        
        Args:
            job: Job to execute
            
        Returns:
            True if job executed successfully, False if failed
            
        Raises:
            Exception: On critical execution errors
        """
        pass
    
    def can_handle_job(self, job: Job) -> bool:
        """Can worker handle given job."""
        return job.job_type in self.get_supported_job_types()
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Information about worker for monitoring."""
        return {
            'worker_id': self.worker_id,
            'supported_job_types': [jt.value for jt in self.get_supported_job_types()],
            'current_job_id': self.current_job.id if self.current_job else None,
            'status': 'busy' if self.current_job else 'idle'
        }


# Predefined configurations for different job types
JOB_TYPE_CONFIGS = {
    JobType.CHANNEL_DOWNLOAD: {
        'timeout_seconds': 3600,  # 1 hour
        'max_retries': 3,
        'priority': JobPriority.HIGH
    },
    JobType.PLAYLIST_DOWNLOAD: {
        'timeout_seconds': 1800,  # 30 minutes
        'max_retries': 3,
        'priority': JobPriority.HIGH
    },
    JobType.METADATA_EXTRACTION: {
        'timeout_seconds': 300,   # 5 minutes
        'max_retries': 2,
        'priority': JobPriority.NORMAL
    },
    JobType.FILE_CLEANUP: {
        'timeout_seconds': 600,   # 10 minutes
        'max_retries': 1,
        'priority': JobPriority.LOW
    },
    JobType.DATABASE_BACKUP: {
        'timeout_seconds': 1200,  # 20 minutes
        'max_retries': 2,
        'priority': JobPriority.URGENT
    },
    JobType.QUICK_SYNC: {
        'timeout_seconds': 300,   # 5 minutes
        'max_retries': 2,
        'priority': JobPriority.HIGH
    }
}


def create_job_with_defaults(job_type: JobType, **kwargs) -> Job:
    """Creates job with default parameters for type."""
    config = JOB_TYPE_CONFIGS.get(job_type, {})
    
    # Apply default values if they are not provided
    for key, default_value in config.items():
        if key not in kwargs:
            kwargs[key] = default_value
    
    return Job.create(job_type=job_type, **kwargs) 