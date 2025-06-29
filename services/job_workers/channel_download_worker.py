#!/usr/bin/env python3
"""
Channel Download Worker

Worker for downloading YouTube channels through Job Queue system.
Integrates with existing download_content.py.
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path
from typing import List
from datetime import datetime

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
import download_content  # Use existing download logic


class ChannelDownloadWorker(JobWorker):
    """Worker for downloading YouTube channels."""
    
    def __init__(self):
        super().__init__("channel_download_worker")
        self.supported_types = [
            JobType.CHANNEL_DOWNLOAD,
            JobType.CHANNEL_SYNC
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Returns supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Executes channel download.
        
        Expected parameters in job.job_data:
        - channel_url: Channel URL for download
        - channel_id: Channel ID in database
        - group_name: Channel group name
        - download_archive: Whether to use archive (default: True)
        - max_downloads: Maximum number of downloads (optional)
        
        Returns:
            True if download successful, False otherwise
        """
        try:
            # Extract parameters from job data
            channel_url = job.job_data.get('channel_url')
            channel_id = job.job_data.get('channel_id')
            group_name = job.job_data.get('group_name', 'Default')
            download_archive = job.job_data.get('download_archive', True)
            max_downloads = job.job_data.get('max_downloads')
            
            if not channel_url:
                raise ValueError("channel_url is required")
            
            if not channel_id:
                raise ValueError("channel_id is required")
            
            print(f"Starting channel download: {channel_url}")
            print(f"Channel ID: {channel_id}, Group: {group_name}")
            print(f"Download archive: {download_archive}, Max downloads: {max_downloads}")
            
            # Determine working directory (project root)
            project_root = Path(__file__).parent.parent.parent
            
            # Load configuration from .env
            config = self._load_config(project_root)
            
            # Determine paths
            if 'ROOT_DIR' in config:
                root_dir = Path(config['ROOT_DIR'])
            else:
                root_dir = project_root  # fallback
            
            playlists_dir = root_dir / 'Playlists'
            
            # Create group folder if needed
            group_folder = playlists_dir / group_name
            group_folder.mkdir(parents=True, exist_ok=True)
            
            print(f"Using playlists directory: {playlists_dir}")
            print(f"Group folder: {group_folder}")
            
            # Call download_content.py via subprocess for isolation
            # This allows capturing all output and logs
            cmd = [
                sys.executable,
                str(project_root / 'download_content.py'),
                channel_url,
                '--root', str(root_dir)
            ]
            
            # Add optional parameters
            if not download_archive:
                cmd.append('--no-archive')
            
            if max_downloads:
                cmd.extend(['--max-downloads', str(max_downloads)])
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Run download with output capture
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours timeout for large channels
            )
            
            # Output result for logging
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            print(f"Process exit code: {result.returncode}")
            
            # Check result
            if result.returncode == 0:
                print("Channel download completed successfully")
                
                # Update channel statistics in database
                self._update_channel_stats(channel_id, config.get('DB_PATH'))
                
                # AUTOMATIC METADATA CLEANUP after download
                self._cleanup_metadata_after_download(channel_url, group_name, root_dir)
                
                return True
            else:
                print(f"Channel download failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Channel download timed out (2 hours)")
            return False
        except Exception as e:
            print(f"Exception during channel download: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _load_config(self, project_root: Path) -> dict:
        """Loads configuration from .env file."""
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
    
    def _update_channel_stats(self, channel_id: int, db_path: str = None):
        """Updates channel statistics after download."""
        try:
            if not db_path:
                # Fallback to default path
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            # Call update_channel_sync via subprocess
            # This will update track_count and other statistics
            cmd = [
                sys.executable,
                '-c',
                f"""
import sys
sys.path.append('{Path(__file__).parent.parent.parent}')
from database import update_channel_sync
update_channel_sync({channel_id})
print('Channel stats updated successfully')
"""
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"Channel {channel_id} stats updated successfully")
                if result.stdout:
                    print(result.stdout.strip())
            else:
                print(f"Failed to update channel stats: {result.stderr}")
                
        except Exception as e:
            print(f"Warning: Failed to update channel stats: {e}")
    
    def _cleanup_metadata_after_download(self, channel_url: str, group_name: str, root_dir: Path):
        """
        Automatic metadata cleanup after channel download.
        
        Args:
            channel_url: Channel URL
            group_name: Channel group name
            root_dir: Root directory
        """
        try:
            print("Starting automatic metadata cleanup after download...")
            
            # Determine cleanup script path
            project_root = Path(__file__).parent.parent.parent
            cleanup_script = project_root / 'scripts' / 'cleanup_channel_metadata.py'
            
            if not cleanup_script.exists():
                print(f"Warning: Cleanup script not found at {cleanup_script}")
                return
            
            # Extract channel name from URL for cleanup
            # Example: https://www.youtube.com/@kalush.official -> kalush.official
            channel_name = None
            if '@' in channel_url:
                channel_name = channel_url.split('@')[-1].split('/')[0]
            elif '/c/' in channel_url:
                channel_name = channel_url.split('/c/')[-1].split('/')[0]
            elif '/channel/' in channel_url:
                # For channel IDs, try to find folder in group
                playlists_dir = root_dir / 'Playlists' / group_name
                if playlists_dir.exists():
                    # Find latest created channel folder
                    channel_folders = [f for f in playlists_dir.iterdir() 
                                     if f.is_dir() and f.name.startswith('Channel-')]
                    if channel_folders:
                        # Get most recent folder
                        latest_folder = max(channel_folders, key=lambda x: x.stat().st_mtime)
                        channel_name = latest_folder.name.replace('Channel-', '')
            
            if not channel_name:
                print(f"Warning: Could not extract channel name from URL: {channel_url}")
                return
            
            print(f"Cleaning up metadata for channel: {channel_name}")
            
            # Execute cleanup script
            cmd = [
                sys.executable,
                str(cleanup_script),
                '--channel', channel_name,
                '--root', str(root_dir)
            ]
            
            print(f"Executing cleanup command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout for cleanup
            )
            
            if result.returncode == 0:
                print("✅ Automatic metadata cleanup completed successfully")
                if result.stdout:
                    # Show cleanup statistics
                    lines = result.stdout.strip().split('\n')
                    for line in lines[-5:]:  # Last 5 lines with summary
                        print(f"  {line}")
            else:
                print(f"⚠️ Metadata cleanup finished with warnings (exit code: {result.returncode})")
                if result.stderr:
                    print(f"Cleanup stderr: {result.stderr}")
                    
        except subprocess.TimeoutExpired:
            print("⚠️ Metadata cleanup timed out (5 minutes)")
        except Exception as e:
            print(f"⚠️ Exception during automatic metadata cleanup: {e}")
    
    def get_worker_info(self) -> dict:
        """Worker information for monitoring."""
        info = super().get_worker_info()
        info.update({
            'description': 'Downloads YouTube channels using yt-dlp',
            'max_concurrent_jobs': 1,  # Download channels one by one
            'average_duration': '30-60 minutes',
            'supported_features': [
                'download_archive',
                'max_downloads_limit',
                'channel_statistics_update',
                'progress_tracking'
            ]
        })
        return info 