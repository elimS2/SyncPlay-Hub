#!/usr/bin/env python3
"""
Auto Backup Service

Service for automatic daily database backups through Job Queue system.
Schedules and manages automated backup tasks based on configuration.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from .job_queue_service import get_job_queue_service
from .job_types import JobType, JobData, JobPriority, create_job_with_defaults


class AutoBackupService:
    """Service for automatic daily database backups."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize auto backup service.
        
        Args:
            config: Configuration dictionary with settings:
                - enabled: whether auto backups are enabled (default: True)
                - schedule_time: time to run backups in HH:MM format (default: "02:00")
                - retention_days: days to keep backups (default: 30)
                - check_interval: minutes between schedule checks (default: 60)
        """
        self.config = config or {}
        
        # Default configuration
        self.enabled = self.config.get('enabled', True)
        self.schedule_time = self.config.get('schedule_time', "02:00")  # 2 AM UTC
        self.retention_days = self.config.get('retention_days', 30)
        self.check_interval = self.config.get('check_interval', 60)  # minutes
        
        # State management
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._last_backup_date: Optional[str] = None
        
        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Job queue service
        self._job_queue_service = None
    
    def start(self):
        """Start the auto backup service."""
        if not self.enabled:
            self.logger.info("Auto backup service is disabled in configuration")
            return
        
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self.logger.warning("Auto backup service is already running")
            return
        
        self.logger.info("Starting Auto Backup Service")
        self.logger.info(f"Schedule: Daily at {self.schedule_time} UTC")
        self.logger.info(f"Retention: {self.retention_days} days")
        self.logger.info(f"Check interval: {self.check_interval} minutes")
        
        # Get job queue service
        self._job_queue_service = get_job_queue_service(max_workers=1)
        
        # Start scheduler thread
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="AutoBackupScheduler",
            daemon=True
        )
        self._scheduler_thread.start()
        
        self.logger.info("Auto Backup Service started successfully")
    
    def stop(self):
        """Stop the auto backup service."""
        if not self._scheduler_thread or not self._scheduler_thread.is_alive():
            self.logger.info("Auto backup service is not running")
            return
        
        self.logger.info("Stopping Auto Backup Service...")
        self._stop_event.set()
        
        # Wait for scheduler thread to finish
        if self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=10)
            
            if self._scheduler_thread.is_alive():
                self.logger.warning("Scheduler thread did not stop gracefully")
            else:
                self.logger.info("Auto Backup Service stopped successfully")
    
    def _scheduler_loop(self):
        """Main scheduler loop that runs in background thread."""
        self.logger.info("Auto backup scheduler started")
        
        while not self._stop_event.is_set():
            try:
                # Check if it's time to create backup
                if self._should_create_backup():
                    self._schedule_backup_job()
                
                # Wait for next check (with early exit if stop requested)
                wait_seconds = self.check_interval * 60
                if self._stop_event.wait(wait_seconds):
                    break  # Stop event was set
                    
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                # Wait a bit before retrying to avoid tight error loop
                if self._stop_event.wait(300):  # 5 minutes
                    break
        
        self.logger.info("Auto backup scheduler stopped")
    
    def _should_create_backup(self) -> bool:
        """Check if we should create a backup now."""
        try:
            now = datetime.utcnow()
            current_date = now.strftime('%Y-%m-%d')
            current_time = now.strftime('%H:%M')
            
            # Check if we already created backup today
            if self._last_backup_date == current_date:
                return False
            
            # Check if it's the right time
            schedule_hour, schedule_minute = map(int, self.schedule_time.split(':'))
            
            # Allow a window around the scheduled time (to handle check intervals)
            schedule_time = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
            
            # We should backup if:
            # 1. Current time is after the scheduled time
            # 2. We haven't backed up today yet
            # 3. We're within the backup window (schedule + check_interval)
            
            time_diff = now - schedule_time
            
            if time_diff.total_seconds() >= 0 and time_diff.total_seconds() <= (self.check_interval * 60):
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking backup schedule: {e}")
            return False
    
    def _schedule_backup_job(self):
        """Schedule a backup job in the job queue."""
        try:
            self.logger.info("Scheduling automatic database backup job")
            
            # Create job data
            job_data = JobData(
                backup_type='full',
                retention_days=self.retention_days,
                cleanup_old=False,
                force_backup=False,
                source='auto_backup_service'
            )
            
            # Create and schedule job
            job = create_job_with_defaults(
                JobType.DATABASE_BACKUP,
                job_data=job_data,
                priority=JobPriority.NORMAL,
                timeout_seconds=1800,  # 30 minutes timeout
                max_retries=2
            )
            
            job_id = self._job_queue_service.add_job(
                job, 
                callback=self._backup_job_callback
            )
            
            # Update last backup date to prevent duplicate scheduling
            self._last_backup_date = datetime.utcnow().strftime('%Y-%m-%d')
            
            self.logger.info(f"Automatic backup job scheduled with ID: {job_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to schedule backup job: {e}")
    
    def _backup_job_callback(self, job_id: int, success: bool, error_message: Optional[str]):
        """Callback for backup job completion."""
        if success:
            self.logger.info(f"Automatic backup job {job_id} completed successfully")
        else:
            self.logger.error(f"Automatic backup job {job_id} failed: {error_message}")
    
    def force_backup_now(self) -> int:
        """
        Force create a backup immediately (for testing or manual triggers).
        
        Returns:
            Job ID of created backup job
        """
        try:
            self.logger.info("Forcing immediate database backup")
            
            if not self._job_queue_service:
                self._job_queue_service = get_job_queue_service(max_workers=1)
            
            # Create job data with force_backup=True
            job_data = JobData(
                backup_type='full',
                retention_days=self.retention_days,
                cleanup_old=False,
                force_backup=True,
                source='manual_force'
            )
            
            # Create and schedule job with high priority
            job = create_job_with_defaults(
                JobType.DATABASE_BACKUP,
                job_data=job_data,
                priority=JobPriority.HIGH,
                timeout_seconds=1800,
                max_retries=2
            )
            
            job_id = self._job_queue_service.add_job(job)
            
            self.logger.info(f"Force backup job scheduled with ID: {job_id}")
            return job_id
            
        except Exception as e:
            self.logger.error(f"Failed to force backup: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of auto backup service."""
        is_running = self._scheduler_thread and self._scheduler_thread.is_alive()
        
        return {
            'enabled': self.enabled,
            'running': is_running,
            'schedule_time': self.schedule_time,
            'retention_days': self.retention_days,
            'check_interval': self.check_interval,
            'last_backup_date': self._last_backup_date,
            'next_check': self._get_next_check_time(),
            'next_scheduled_backup': self._get_next_backup_time()
        }
    
    def _get_next_check_time(self) -> str:
        """Get next scheduler check time."""
        if not self._scheduler_thread or not self._scheduler_thread.is_alive():
            return "Service not running"
        
        next_check = datetime.utcnow() + timedelta(minutes=self.check_interval)
        return next_check.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    def _get_next_backup_time(self) -> str:
        """Get next scheduled backup time."""
        try:
            now = datetime.utcnow()
            schedule_hour, schedule_minute = map(int, self.schedule_time.split(':'))
            
            # Calculate next backup time
            next_backup = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
            
            # If the scheduled time has already passed today, schedule for tomorrow
            if next_backup <= now:
                next_backup += timedelta(days=1)
            
            return next_backup.strftime('%Y-%m-%d %H:%M:%S UTC')
            
        except Exception:
            return "Unknown"
    
    def update_config(self, new_config: Dict[str, Any]):
        """Update configuration and restart if needed."""
        old_enabled = self.enabled
        
        # Update configuration
        self.config.update(new_config)
        self.enabled = self.config.get('enabled', True)
        self.schedule_time = self.config.get('schedule_time', "02:00")
        self.retention_days = self.config.get('retention_days', 30)
        self.check_interval = self.config.get('check_interval', 60)
        
        self.logger.info(f"Auto backup configuration updated: {new_config}")
        
        # Restart service if enabled state changed
        if old_enabled != self.enabled:
            if self.enabled:
                self.start()
            else:
                self.stop()


# Singleton instance
_auto_backup_service: Optional[AutoBackupService] = None


def get_auto_backup_service(config: Dict[str, Any] = None) -> AutoBackupService:
    """Get singleton instance of auto backup service."""
    global _auto_backup_service
    
    if _auto_backup_service is None:
        _auto_backup_service = AutoBackupService(config)
    
    return _auto_backup_service


def start_auto_backup_service(config: Dict[str, Any] = None):
    """Start the auto backup service."""
    service = get_auto_backup_service(config)
    service.start()


def stop_auto_backup_service():
    """Stop the auto backup service."""
    global _auto_backup_service
    
    if _auto_backup_service is not None:
        _auto_backup_service.stop() 