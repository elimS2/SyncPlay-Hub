#!/usr/bin/env python3
"""
Metadata Extraction Worker

Worker for extracting YouTube channel metadata through Job Queue system.
Integrates with existing extract_channel_metadata.py.
"""

import sys
import subprocess
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
from utils.cookies_manager import get_random_cookie_file


class MetadataExtractionWorker(JobWorker):
    """Worker for extracting YouTube channel metadata."""
    
    def __init__(self):
        super().__init__("metadata_extraction_worker")
        self.supported_types = [
            JobType.METADATA_EXTRACTION,
            JobType.CHANNEL_METADATA_UPDATE,
            JobType.PLAYLIST_METADATA_UPDATE
        ]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Returns supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Executes metadata extraction.
        
        Expected parameters in job.job_data:
        - channel_url: Channel URL for metadata extraction
        - channel_id: Channel ID in database (optional)
        - extract_type: Type of extraction ('channel', 'playlist', 'video')
        - force_update: Whether to force update existing metadata
        - max_entries: Maximum number of entries to extract (optional)
        - playlist_items: Specific video indices to process (optional)
        
        Returns:
            True if extraction successful, False otherwise
        """
        try:
            # Extract parameters from job data
            channel_url = job.job_data.get('channel_url')
            channel_id = job.job_data.get('channel_id')
            extract_type = job.job_data.get('extract_type', 'channel')
            force_update = job.job_data.get('force_update', False)
            max_entries = job.job_data.get('max_entries')
            playlist_items = job.job_data.get('playlist_items')  # New: specify video indices
            
            if not channel_url:
                raise ValueError("channel_url is required")
            
            print(f"Starting metadata extraction for: {channel_url}")
            print(f"Channel ID: {channel_id}, Type: {extract_type}")
            print(f"Force update: {force_update}, Max entries: {max_entries}")
            if playlist_items:
                print(f"Playlist items filter: {playlist_items}")
            
            # Get cookies for the extraction
            cookies_path = get_random_cookie_file()
            if not cookies_path:
                print("Warning: No cookies available - extraction may fail for age-restricted content")
            else:
                print(f"Using cookies file: {cookies_path}")
            
            # Determine working directory (project root)
            project_root = Path(__file__).parent.parent.parent
            
            # Build command to run extract_channel_metadata.py
            cmd = [
                sys.executable,
                str(project_root / "scripts" / "extract_channel_metadata.py"),
                channel_url
            ]
            
            # Add optional parameters
            if force_update:
                cmd.append("--force-update")
            
            if max_entries:
                cmd.extend(["--max-entries", str(max_entries)])
            
            if cookies_path:
                cmd.extend(["--cookies", cookies_path])
            
            # Add playlist items parameter
            if playlist_items:
                cmd.extend(['--playlist-items', playlist_items])
            
            # Add database path from configuration
            config = self._load_config(project_root)
            db_path = config.get('DB_PATH')
            if db_path:
                cmd.extend(['--db-path', db_path])
                print(f"Using database path: {db_path}")
            else:
                print("Warning: No DB_PATH in .env file, using default database")
            
            print(f"Executing command: {' '.join(cmd)}")
            
            # Execute the script
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout for metadata extraction
            )
            
            # Output the results
            if result.stdout:
                print("=== STDOUT ===")
                print(result.stdout)
            
            if result.stderr:
                print("=== STDERR ===")
                print(result.stderr)
            
            # Check result
            if result.returncode == 0:
                print("Metadata extraction completed successfully")
                return True
            else:
                print(f"Metadata extraction failed with exit code {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Metadata extraction timed out (30 minutes)")
            return False
        except Exception as e:
            print(f"Exception during metadata extraction: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _load_config(self, project_root: Path) -> dict:
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
    
    def _update_metadata_timestamp(self, channel_id: int, db_path: str = None):
        """Update channel metadata last updated timestamp."""
        try:
            if not db_path:
                # Fallback to default path
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / 'tracks.db')
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Update metadata_last_updated field
                cursor.execute("""
                    UPDATE channels 
                    SET metadata_last_updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (channel_id,))
                
                if cursor.rowcount > 0:
                    print(f"Updated metadata timestamp for channel {channel_id}")
                else:
                    print(f"Warning: Channel {channel_id} not found for timestamp update")
                
                conn.commit()
                
        except Exception as e:
            print(f"Warning: Failed to update metadata timestamp: {e}")
    
    def _parse_videos_count(self, output: str) -> int:
        """Parse number of processed videos from script output."""
        try:
            for line in output.split('\n'):
                # Look for lines like "Loaded X videos metadata for channel"
                if 'videos metadata for channel' in line:
                    words = line.split()
                    for i, word in enumerate(words):
                        if word == 'Loaded' and i + 1 < len(words):
                            try:
                                return int(words[i + 1])
                            except ValueError:
                                continue
                
                # Or "Processing X entries"
                if 'Processing' in line and 'entries' in line:
                    words = line.split()
                    for i, word in enumerate(words):
                        if word == 'Processing' and i + 1 < len(words):
                            try:
                                return int(words[i + 1])
                            except ValueError:
                                continue
            
            return 0
            
        except Exception:
            return 0
    
    def get_worker_info(self) -> dict:
        """Worker information for monitoring."""
        info = super().get_worker_info()
        info.update({
            'description': 'Extracts YouTube metadata using yt-dlp with smart batching and date filtering',
            'max_concurrent_jobs': 2,  # Can run multiple metadata extractions
            'average_duration': '5-15 minutes',
            'supported_features': [
                'smart_batching',
                'date_filtering',
                'cookies_support',
                'playlist_items_filtering',
                'force_update',
                'max_entries_limit'
            ]
        })
        return info 