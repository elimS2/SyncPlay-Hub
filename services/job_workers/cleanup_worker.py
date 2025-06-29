#!/usr/bin/env python3
"""
Cleanup Worker

Worker for cleaning old files, logs and database through Job Queue system.
Performs various types of cleanup depending on job type.
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
import glob

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType


class CleanupWorker(JobWorker):
    """Worker for various cleanup tasks."""
    
    def __init__(self):
        super().__init__("cleanup_worker")
        self.supported_types = [
            JobType.FILE_CLEANUP,
            JobType.DATABASE_CLEANUP,
            JobType.LOG_CLEANUP,
            JobType.METADATA_CLEANUP
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Return supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Execute cleanup task.
        
        Expected parameters in job.job_data depend on task type:
        
        FILE_CLEANUP:
        - cleanup_type: 'orphaned_files', 'old_downloads', 'temp_files'
        - days_old: number of days to determine old files (default: 30)
        - dry_run: only show what would be deleted (default: False)
        - target_directories: list of directories to clean (optional)
        
        DATABASE_CLEANUP:
        - cleanup_type: 'old_history', 'orphaned_records', 'temp_data'
        - days_old: number of days for history cleanup (default: 90)
        - dry_run: only show what would be deleted (default: False)
        
        LOG_CLEANUP:
        - cleanup_type: 'old_logs', 'job_logs', 'archive_logs'
        - days_old: number of days to keep logs (default: 30)
        - dry_run: only show what would be deleted (default: False)
        
        METADATA_CLEANUP:
        - cleanup_type: 'channel_metadata', 'all_metadata'
        - channels: list of channels to clean (optional, for channel_metadata)
        - dry_run: only show what would be deleted (default: False)
        
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            cleanup_type = job.job_data.get('cleanup_type')
            days_old = job.job_data.get('days_old', 30)
            dry_run = job.job_data.get('dry_run', False)
            
            if not cleanup_type:
                raise ValueError("cleanup_type is required")
            
            print(f"Starting cleanup: {job.job_type.value}")
            print(f"Cleanup type: {cleanup_type}")
            print(f"Days old: {days_old}, Dry run: {dry_run}")
            
            # Determine working directory (project root)
            project_root = Path(__file__).parent.parent.parent
            
            # Load configuration from .env
            config = self._load_config(project_root)
            
            # Execute appropriate cleanup type
            if job.job_type == JobType.FILE_CLEANUP:
                success = self._cleanup_files(cleanup_type, days_old, dry_run, config, job.job_data)
            elif job.job_type == JobType.DATABASE_CLEANUP:
                success = self._cleanup_database(cleanup_type, days_old, dry_run, config)
            elif job.job_type == JobType.LOG_CLEANUP:
                success = self._cleanup_logs(cleanup_type, days_old, dry_run, config)
            elif job.job_type == JobType.METADATA_CLEANUP:
                success = self._cleanup_metadata(cleanup_type, days_old, dry_run, config, job.job_data)
            else:
                raise ValueError(f"Unsupported job type: {job.job_type}")
            
            if success:
                print("Cleanup completed successfully")
            else:
                print("Cleanup completed with errors")
            
            return success
            
        except Exception as e:
            print(f"Exception during cleanup: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _cleanup_files(self, cleanup_type: str, days_old: int, dry_run: bool, 
                      config: Dict[str, str], job_data: Dict[str, Any]) -> bool:
        """Execute file cleanup."""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            total_size = 0
            
            if cleanup_type == 'orphaned_files':
                # Remove files that are not in database
                removed_count, total_size = self._cleanup_orphaned_files(
                    config, cutoff_time, dry_run
                )
            
            elif cleanup_type == 'old_downloads':
                # Remove old downloaded files
                target_dirs = job_data.get('target_directories', [])
                removed_count, total_size = self._cleanup_old_downloads(
                    config, cutoff_time, dry_run, target_dirs
                )
            
            elif cleanup_type == 'temp_files':
                # Remove temporary files
                removed_count, total_size = self._cleanup_temp_files(
                    config, cutoff_time, dry_run
                )
            
            else:
                raise ValueError(f"Unknown file cleanup type: {cleanup_type}")
            
            print(f"File cleanup results: {removed_count} files, {total_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e:
            print(f"File cleanup error: {e}")
            return False
    
    def _cleanup_database(self, cleanup_type: str, days_old: int, dry_run: bool,
                         config: Dict[str, str]) -> bool:
        """Execute database cleanup."""
        try:
            db_path = config.get('DB_PATH')
            if not db_path:
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                if cleanup_type == 'old_history':
                    # Remove old play history
                    if dry_run:
                        cursor.execute("""
                            SELECT COUNT(*) FROM play_history 
                            WHERE timestamp < ?
                        """, (cutoff_date.isoformat(),))
                        removed_count = cursor.fetchone()[0]
                    else:
                        cursor.execute("""
                            DELETE FROM play_history 
                            WHERE timestamp < ?
                        """, (cutoff_date.isoformat(),))
                        removed_count = cursor.rowcount
                        conn.commit()
                
                elif cleanup_type == 'orphaned_records':
                    # Remove track records that don't exist on disk
                    removed_count = self._cleanup_orphaned_db_records(cursor, config, dry_run)
                    if not dry_run:
                        conn.commit()
                
                elif cleanup_type == 'temp_data':
                    # Remove temporary data and caches
                    removed_count = self._cleanup_temp_db_data(cursor, cutoff_date, dry_run)
                    if not dry_run:
                        conn.commit()
                
                else:
                    raise ValueError(f"Unknown database cleanup type: {cleanup_type}")
            
            print(f"Database cleanup results: {removed_count} records removed")
            return True
            
        except Exception as e:
            print(f"Database cleanup error: {e}")
            return False
    
    def _cleanup_logs(self, cleanup_type: str, days_old: int, dry_run: bool,
                     config: Dict[str, str]) -> bool:
        """Execute log cleanup."""
        try:
            # Determine log directory
            log_dir = config.get('LOG_DIR')
            if not log_dir:
                project_root = Path(__file__).parent.parent.parent
                log_dir = str(project_root / 'logs')
            
            log_path = Path(log_dir)
            cutoff_time = datetime.now() - timedelta(days=days_old)
            removed_count = 0
            total_size = 0
            
            if cleanup_type == 'old_logs':
                # Remove old log files
                log_patterns = ['*.log', '*.log.*', '*.out', '*.err']
                removed_count, total_size = self._cleanup_old_log_files(
                    log_path, cutoff_time, dry_run, log_patterns
                )
            
            elif cleanup_type == 'job_logs':
                # Remove old job log directories
                jobs_dir = log_path / 'jobs'
                if jobs_dir.exists():
                    removed_count, total_size = self._cleanup_job_log_dirs(
                        jobs_dir, cutoff_time, dry_run
                    )
            
            elif cleanup_type == 'archive_logs':
                # Remove archived log files
                archive_patterns = ['*.gz', '*.zip', '*.tar', '*.bz2']
                removed_count, total_size = self._cleanup_old_log_files(
                    log_path, cutoff_time, dry_run, archive_patterns
                )
            
            else:
                raise ValueError(f"Unknown log cleanup type: {cleanup_type}")
            
            print(f"Log cleanup results: {removed_count} files, {total_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e:
            print(f"Log cleanup error: {e}")
            return False
    
    def _cleanup_metadata(self, cleanup_type: str, days_old: int, dry_run: bool,
                         config: Dict[str, str], job_data: Dict[str, Any]) -> bool:
        """Execute YouTube channel metadata files cleanup."""
        try:
            removed_count = 0
            total_size = 0
            
            if cleanup_type == 'channel_metadata':
                # Clean metadata in channel folders
                removed_count, total_size = self._cleanup_channel_metadata_files(
                    config, job_data, dry_run
                )
            
            elif cleanup_type == 'all_metadata':
                # Clean all metadata files in project
                removed_count, total_size = self._cleanup_all_metadata_files(
                    config, dry_run
                )
            
            else:
                raise ValueError(f"Unknown metadata cleanup type: {cleanup_type}")
            
            print(f"Metadata cleanup results: {removed_count} files, {total_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e:
            print(f"Metadata cleanup error: {e}")
            return False
    
    def _cleanup_orphaned_files(self, config: Dict[str, str], cutoff_time: datetime, 
                               dry_run: bool) -> tuple[int, int]:
        """Remove files that exist locally but not in database."""
        # TODO: Implement checking file existence for database records
        print("Orphaned files cleanup not yet implemented")
        return 0, 0
    
    def _cleanup_old_downloads(self, config: Dict[str, str], cutoff_time: datetime,
                              dry_run: bool, target_dirs: List[str]) -> tuple[int, int]:
        """Remove old downloaded files from specified directories."""
        removed_count = 0
        total_size = 0
        
        # Use provided directories or default download paths
        if not target_dirs:
            root_dir = config.get('ROOT_DIR', 'D:/music/Youtube')
            target_dirs = [
                f"{root_dir}/Playlists",
                f"{root_dir}/Downloads"
            ]
        
        for dir_path in target_dirs:
            dir_path = Path(dir_path)
            if not dir_path.exists():
                continue
                
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
        
        return removed_count, total_size
    
    def _cleanup_temp_files(self, config: Dict[str, str], cutoff_time: datetime,
                           dry_run: bool) -> tuple[int, int]:
        """Remove temporary files and YouTube metadata files."""
        removed_count = 0
        total_size = 0
        
        # Temporary files and YouTube metadata files
        temp_patterns = [
            '*.tmp',
            '*.temp',
            '*.part',
            '*.download',
            '*.ytdl',
            '__pycache__',
            '*.pyc',
            # YouTube metadata files (yt-dlp creates these)
            '*.json',           # Video metadata JSON files
            '*.info.json',      # Detailed video information
            '*.description',    # Video descriptions
            '*.thumbnail',      # Video thumbnails
            '*.webp',          # WebP images (thumbnails)
            '*.jpg',           # JPEG images (thumbnails) 
            '*.png',           # PNG images (thumbnails)
        ]
        
        # Search in all project folders
        project_root = Path(__file__).parent.parent.parent
        
        for pattern in temp_patterns:
            for file_path in project_root.rglob(pattern):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
                
                elif file_path.is_dir() and pattern == '__pycache__':
                    if dry_run:
                        print(f"Would remove directory: {file_path}")
                    else:
                        try:
                            shutil.rmtree(file_path)
                            print(f"Removed directory: {file_path}")
                        except Exception as e:
                            print(f"Failed to remove directory {file_path}: {e}")
                            continue
                    
                    removed_count += 1
        
        return removed_count, total_size
    
    def _cleanup_orphaned_db_records(self, cursor, config: Dict[str, str], dry_run: bool) -> int:
        """Remove track records that don't exist on disk."""
        # TODO: Implement checking file existence for database records
        print("Orphaned database records cleanup not yet implemented")
        return 0
    
    def _cleanup_temp_db_data(self, cursor, cutoff_date: datetime, dry_run: bool) -> int:
        """Remove temporary data from database."""
        removed_count = 0
        
        # Examples of temporary data to clean
        # (can add project-specific tables here)
        
        # Clean old error logs if such table exists
        try:
            if dry_run:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='error_logs'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM error_logs WHERE timestamp < ?", (cutoff_date.isoformat(),))
                    count = cursor.fetchone()[0]
                    removed_count += count
            else:
                cursor.execute("DELETE FROM error_logs WHERE timestamp < ?", (cutoff_date.isoformat(),))
                removed_count += cursor.rowcount
        except sqlite3.OperationalError:
            pass  # Table doesn't exist
        
        return removed_count
    
    def _cleanup_old_log_files(self, log_path: Path, cutoff_time: datetime,
                              dry_run: bool, patterns: List[str]) -> tuple[int, int]:
        """Remove old log files by patterns."""
        removed_count = 0
        total_size = 0
        
        for pattern in patterns:
            for file_path in log_path.glob(pattern):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_size = file_path.stat().st_size
                        
                        if dry_run:
                            print(f"Would remove: {file_path} ({file_size} bytes)")
                        else:
                            try:
                                file_path.unlink()
                                print(f"Removed: {file_path}")
                            except Exception as e:
                                print(f"Failed to remove {file_path}: {e}")
                                continue
                        
                        removed_count += 1
                        total_size += file_size
        
        return removed_count, total_size
    
    def _cleanup_job_log_dirs(self, jobs_dir: Path, cutoff_time: datetime,
                             dry_run: bool) -> tuple[int, int]:
        """Remove old job log directories."""
        removed_count = 0
        total_size = 0
        
        for job_dir in jobs_dir.iterdir():
            if job_dir.is_dir() and job_dir.name.startswith('job_'):
                dir_time = datetime.fromtimestamp(job_dir.stat().st_mtime)
                if dir_time < cutoff_time:
                    # Calculate directory size
                    dir_size = sum(f.stat().st_size for f in job_dir.rglob('*') if f.is_file())
                    
                    if dry_run:
                        print(f"Would remove directory: {job_dir} ({dir_size} bytes)")
                    else:
                        try:
                            shutil.rmtree(job_dir)
                            print(f"Removed directory: {job_dir}")
                        except Exception as e:
                            print(f"Failed to remove directory {job_dir}: {e}")
                            continue
                    
                    removed_count += 1
                    total_size += dir_size
        
        return removed_count, total_size
    
    def _load_config(self, project_root: Path) -> Dict[str, str]:
        """Load configuration from .env file."""
        config = {}
        env_path = project_root / '.env'
        
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip().lstrip('\ufeff')  # Remove BOM
                        if line and '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            config[key.strip()] = value.strip()
            except Exception as e:
                print(f"Warning: Failed to load .env file: {e}")
        
        return config
    
    def _cleanup_channel_metadata_files(self, config: Dict[str, str], 
                                       job_data: Dict[str, Any], dry_run: bool) -> tuple[int, int]:
        """Clean metadata files in channel folders."""
        removed_count = 0
        total_size = 0
        
        # Get directories for cleanup
        root_dir = config.get('ROOT_DIR', 'D:/music/Youtube')
        playlists_dir = config.get('PLAYLISTS_DIR', f'{root_dir}/Playlists')
        base_path = Path(playlists_dir)
        
        # Get specific channels for cleanup (if specified)
        target_channels = job_data.get('channels', [])
        
        # Metadata file patterns
        metadata_patterns = [
            '*.json',           # Video metadata JSON files
            '*.info.json',      # Detailed video information
            '*.description',    # Video descriptions
            '*.thumbnail',      # Video thumbnails
            '*.webp',          # WebP images (thumbnails)
            '*.jpg',           # JPEG images (thumbnails) 
            '*.png',           # PNG images (thumbnails)
        ]
        
        if not base_path.exists():
            print(f"Playlists directory not found: {base_path}")
            return 0, 0
        
        # If specific channels are specified
        if target_channels:
            for channel_name in target_channels:
                # Add Channel- prefix if missing
                if not channel_name.startswith("Channel-"):
                    channel_name = f"Channel-{channel_name}"
                
                # Search for channel folder in various groups
                channel_folders = []
                for group_folder in base_path.iterdir():
                    if group_folder.is_dir():
                        channel_folder = group_folder / channel_name
                        if channel_folder.exists() and channel_folder.is_dir():
                            channel_folders.append(channel_folder)
                
                # Also check root folder
                channel_folder = base_path / channel_name
                if channel_folder.exists() and channel_folder.is_dir():
                    channel_folders.append(channel_folder)
                
                # Clean found channel folders
                for folder in channel_folders:
                    count, size = self._cleanup_metadata_in_folder(folder, metadata_patterns, dry_run)
                    removed_count += count
                    total_size += size
        else:
            # Clean all channel folders
            for channel_folder in base_path.rglob("Channel-*"):
                if channel_folder.is_dir():
                    count, size = self._cleanup_metadata_in_folder(channel_folder, metadata_patterns, dry_run)
                    removed_count += count
                    total_size += size
        
        return removed_count, total_size
    
    def _cleanup_all_metadata_files(self, config: Dict[str, str], dry_run: bool) -> tuple[int, int]:
        """Clean all metadata files in project."""
        removed_count = 0
        total_size = 0
        
        # Get root directory
        root_dir = config.get('ROOT_DIR', 'D:/music/Youtube')
        project_root = Path(root_dir)
        
        # Metadata file patterns (more conservative approach for whole project)
        metadata_patterns = [
            '*.info.json',      # Only specific yt-dlp files
            '*.description',    # Video descriptions
            '*.thumbnail',      # Video thumbnails
            '*.webp',          # WebP images (thumbnails)
        ]
        
        if not project_root.exists():
            print(f"Root directory not found: {project_root}")
            return 0, 0
        
        # Clean only in playlists folders for safety
        playlists_dir = Path(config.get('PLAYLISTS_DIR', f'{root_dir}/Playlists'))
        if playlists_dir.exists():
            count, size = self._cleanup_metadata_in_folder(playlists_dir, metadata_patterns, dry_run)
            removed_count += count
            total_size += size
        
        return removed_count, total_size
    
    def _cleanup_metadata_in_folder(self, folder: Path, patterns: List[str], dry_run: bool) -> tuple[int, int]:
        """Clean metadata files in specific folder."""
        removed_count = 0
        total_size = 0
        
        print(f"Cleaning metadata in: {folder}")
        
        for pattern in patterns:
            for file_path in folder.rglob(pattern):
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    
                    if dry_run:
                        print(f"  [Dry Run] Would remove: {file_path.relative_to(folder)} ({file_size:,} bytes)")
                    else:
                        try:
                            file_path.unlink()
                            print(f"  [Removed] {file_path.relative_to(folder)} ({file_size:,} bytes)")
                        except Exception as e:
                            print(f"  [Error] Failed to remove {file_path}: {e}")
                            continue
                    
                    removed_count += 1
                    total_size += file_size
        
        return removed_count, total_size
    
    def get_worker_info(self) -> Dict[str, Any]:
        """Worker information for monitoring."""
        info = super().get_worker_info()
        info.update({
            'description': 'Performs various cleanup tasks (files, database, logs, metadata)',
            'max_concurrent_jobs': 1,  # Execute cleanup tasks sequentially
            'average_duration': '5-30 minutes',
            'supported_features': [
                'file_cleanup',
                'database_cleanup',
                'log_cleanup',
                'metadata_cleanup',
                'channel_metadata_cleanup',
                'youtube_metadata_files',
                'dry_run_mode',
                'orphaned_detection',
                'size_reporting'
            ]
        })
        return info 