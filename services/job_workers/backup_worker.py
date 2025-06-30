#!/usr/bin/env python3
"""
Backup Worker

Worker for automated database backup tasks through Job Queue system.
Handles creation of timestamped database backups with customizable retention.
"""

import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType


class BackupWorker(JobWorker):
    """Worker for database backup tasks."""
    
    def __init__(self):
        super().__init__("backup_worker")
        self.supported_types = [
            JobType.DATABASE_BACKUP
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Return supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Execute database backup task.
        
        Expected parameters in job.job_data:
        - backup_type: 'full' (default), 'incremental' (future)
        - retention_days: number of days to keep backups (default: 30)
        - cleanup_old: whether to cleanup old backups (default: False)
        - force_backup: create backup even if recent one exists (default: False)
        
        Returns:
            True if backup successful, False otherwise
        """
        try:
            backup_type = job.job_data.get('backup_type', 'full')
            retention_days = job.job_data.get('retention_days', 30)
            cleanup_old = job.job_data.get('cleanup_old', False)
            force_backup = job.job_data.get('force_backup', False)
            
            job.log_info(f"Starting database backup: {backup_type}")
            job.log_info(f"Retention: {retention_days} days, cleanup_old: {cleanup_old}")
            
            # Determine working directory (project root)
            project_root = Path(__file__).parent.parent.parent
            
            # Load configuration
            config = self._load_config(project_root)
            
            # Check if we need to create backup
            if not force_backup and not self._should_create_backup(config, job):
                job.log_info("Recent backup exists, skipping automatic backup")
                return True
            
            # Create backup
            backup_result = self._create_database_backup(config, job)
            
            if not backup_result['success']:
                job.log_error(f"Backup creation failed: {backup_result['error']}")
                return False
            
            job.log_info(f"Backup created successfully: {backup_result['backup_path']}")
            job.log_info(f"Backup size: {backup_result['size_bytes'] / (1024*1024):.2f} MB")
            
            # Cleanup old backups if requested
            if cleanup_old:
                cleaned_count = self._cleanup_old_backups(config, retention_days, job)
                if cleaned_count > 0:
                    job.log_info(f"Cleaned up {cleaned_count} old backups")
            
            return True
            
        except Exception as e:
            job.log_exception(e, "database backup execution")
            return False
    
    def _should_create_backup(self, config: Dict[str, str], job: Job) -> bool:
        """Check if we should create a backup based on schedule and existing backups."""
        try:
            # For automatic daily backups, check if we already have a backup today
            root_dir = self._get_root_dir(config)
            
            # Import database functions
            sys.path.append(str(root_dir))
            from database import list_backups
            
            backups = list_backups(root_dir)
            
            if not backups:
                job.log_info("No existing backups found, creating first backup")
                return True
            
            # Check if we have a backup from today
            today = datetime.utcnow().date()
            for backup in backups:
                backup_date = datetime.fromisoformat(backup['timestamp']).date()
                if backup_date == today:
                    job.log_info(f"Backup already exists for today: {backup['timestamp_display']}")
                    return False
            
            return True
            
        except Exception as e:
            job.log_error(f"Error checking backup schedule: {e}")
            # If we can't determine, err on the side of creating backup
            return True
    
    def _create_database_backup(self, config: Dict[str, str], job: Job) -> Dict[str, Any]:
        """Create database backup using existing backup functionality."""
        try:
            root_dir = self._get_root_dir(config)
            
            # Import database functions
            sys.path.append(str(root_dir))
            from database import create_backup
            
            job.log_info("Creating database backup...")
            result = create_backup(root_dir)
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'backup_path': '',
                'error': str(e)
            }
    
    def _cleanup_old_backups(self, config: Dict[str, str], retention_days: int, job: Job) -> int:
        """Remove backups older than retention period."""
        try:
            from datetime import timedelta
            
            root_dir = self._get_root_dir(config)
            
            # Import database functions
            sys.path.append(str(root_dir))
            from database import list_backups
            
            backups = list_backups(root_dir)
            
            if not backups:
                return 0
            
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            cleaned_count = 0
            
            for backup in backups:
                backup_date = datetime.fromisoformat(backup['timestamp'])
                
                if backup_date < cutoff_date:
                    try:
                        backup_path = Path(backup['backup_path'])
                        backup_folder = backup_path.parent
                        
                        # Remove the entire backup folder
                        if backup_folder.exists():
                            import shutil
                            shutil.rmtree(backup_folder)
                            cleaned_count += 1
                            job.log_info(f"Removed old backup: {backup['folder_name']}")
                    
                    except Exception as e:
                        job.log_error(f"Failed to remove backup {backup['folder_name']}: {e}")
            
            return cleaned_count
            
        except Exception as e:
            job.log_error(f"Error during backup cleanup: {e}")
            return 0
    
    def _get_root_dir(self, config: Dict[str, str]) -> Path:
        """Get root directory for backup operations."""
        # Try to get from config
        root_path = config.get('ROOT_DIR')
        if root_path:
            return Path(root_path)
        
        # Fallback to project root
        return Path(__file__).parent.parent.parent
    
    def _load_config(self, project_root: Path) -> Dict[str, str]:
        """Load configuration from .env file."""
        config = {}
        env_path = project_root / '.env'
        
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip().lstrip('\ufeff')
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            config[key.strip()] = value.strip()
            except Exception as e:
                print(f"Warning: Could not load .env file: {e}")
        
        return config
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Get worker information for monitoring."""
        return {
            'worker_id': self.worker_id,
            'worker_type': 'BackupWorker',
            'supported_job_types': [jt.value for jt in self.supported_types],
            'status': 'idle',
            'version': '1.0.0',
            'description': 'Automated database backup worker with retention management'
        } 