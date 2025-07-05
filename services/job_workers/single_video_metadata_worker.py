#!/usr/bin/env python3
"""
Single Video Metadata Worker

Worker for extracting YouTube video metadata for individual videos through Job Queue system.
Part of Extended Metadata Extraction System (Phase 3).
"""

import sys
import subprocess
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add root folder to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from services.job_types import JobWorker, Job, JobType
from utils.cookies_manager import get_random_cookie_file
from utils.logging_utils import log_message


class SingleVideoMetadataWorker(JobWorker):
    """Worker for extracting metadata from single YouTube videos."""
    
    def __init__(self):
        super().__init__("single_video_metadata_worker")
        self.supported_types = [JobType.SINGLE_VIDEO_METADATA_EXTRACTION]
    
    def get_supported_job_types(self) -> List[JobType]:
        """Returns supported job types."""
        return self.supported_types
    
    def execute_job(self, job: Job) -> bool:
        """
        Executes single video metadata extraction.
        
        Expected parameters in job.job_data:
        - video_id: YouTube video ID (required)
        - force_update: Whether to update existing metadata (optional, default: False)
        
        Returns:
            True if extraction successful, False otherwise
        """
        try:
            # Extract parameters from job data
            video_id = job.job_data.get('video_id')
            force_update = job.job_data.get('force_update', False)
            
            if not video_id:
                job.log_error("video_id is required")
                return False
            
            job.log_info(f"Starting metadata extraction for video: {video_id}")
            job.log_info(f"Force update: {force_update}")
            
            # Check if metadata already exists
            if not force_update and self._metadata_exists(video_id):
                job.log_info(f"Metadata already exists for video {video_id}, skipping")
                return True
            
            # Get cookies for the extraction
            cookies_path = get_random_cookie_file()
            if not cookies_path:
                job.log_info("Warning: No cookies available - extraction may fail for age-restricted content")
            else:
                job.log_info(f"Using cookies file: {cookies_path}")
            
            # Extract metadata using yt-dlp
            metadata = self._extract_video_metadata(video_id, cookies_path, job)
            
            if not metadata:
                job.log_error(f"Failed to extract metadata for video {video_id}")
                return False
            
            # Save metadata to database
            success = self._save_metadata_to_database(video_id, metadata, job)
            
            if success:
                job.log_info(f"Successfully extracted and saved metadata for video {video_id}")
                return True
            else:
                job.log_error(f"Failed to save metadata for video {video_id}")
                return False
                
        except Exception as e:
            job.log_exception(e, f"Exception during metadata extraction for video {video_id}")
            return False
    
    def _metadata_exists(self, video_id: str) -> bool:
        """Check if metadata already exists for this video."""
        try:
            # Use the main database connection from database.py
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM youtube_video_metadata 
                WHERE youtube_id = ? AND (timestamp IS NOT NULL OR release_timestamp IS NOT NULL)
            """, (video_id,))
            
            result = cursor.fetchone() is not None
            conn.close()
            return result
            
        except Exception as e:
            log_message(f"Error checking metadata existence for {video_id}: {e}")
            return False
    
    def _extract_video_metadata(self, video_id: str, cookies_path: str, job: Job) -> Optional[Dict[str, Any]]:
        """Extract video metadata using yt-dlp."""
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            cmd = ["yt-dlp", "--dump-json", video_url]
            
            if cookies_path:
                cmd.extend(["--cookies", cookies_path])
            
            job.log_info(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=True
            )
            
            if not result.stdout.strip():
                job.log_error(f"No output from yt-dlp for video {video_id}")
                return None
            
            try:
                metadata = json.loads(result.stdout)
                job.log_info(f"Successfully parsed metadata for video {video_id}")
                return metadata
                
            except json.JSONDecodeError as e:
                job.log_error(f"Failed to parse JSON metadata for video {video_id}: {e}")
                return None
                
        except subprocess.TimeoutExpired:
            job.log_error(f"Timeout extracting metadata for video {video_id}")
            return None
        except subprocess.CalledProcessError as e:
            job.log_error(f"yt-dlp failed for video {video_id}: {e}")
            if e.stderr:
                job.log_error(f"yt-dlp stderr: {e.stderr}")
            return None
        except Exception as e:
            job.log_exception(e, f"Unexpected error extracting metadata for video {video_id}")
            return None
    
    def _save_metadata_to_database(self, video_id: str, metadata: Dict[str, Any], job: Job) -> bool:
        """Save extracted metadata to database."""
        try:
            # Use the main database connection from database.py
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            
            # Prepare metadata fields
            title = metadata.get('title', '')
            description = metadata.get('description', '')
            channel = metadata.get('channel', '')
            uploader = metadata.get('uploader', '')
            uploader_id = metadata.get('uploader_id', '')
            upload_date = metadata.get('upload_date', '')
            
            # Timestamps
            timestamp = metadata.get('timestamp')
            release_timestamp = metadata.get('release_timestamp')
            
            # Counts and metrics
            view_count = metadata.get('view_count', 0)
            like_count = metadata.get('like_count', 0)
            dislike_count = metadata.get('dislike_count', 0)
            comment_count = metadata.get('comment_count', 0)
            
            # Technical details
            duration = metadata.get('duration', 0)
            width = metadata.get('width', 0)
            height = metadata.get('height', 0)
            fps = metadata.get('fps', 0)
            
            # Categories and tags
            categories = json.dumps(metadata.get('categories', []))
            tags = json.dumps(metadata.get('tags', []))
            
            # Full metadata as JSON
            full_metadata = json.dumps(metadata, ensure_ascii=False, default=str)
            
            # Insert or update metadata
            cursor.execute("""
                INSERT OR REPLACE INTO youtube_video_metadata (
                    youtube_id, title, description, channel, uploader, uploader_id,
                    timestamp, release_timestamp, view_count, duration, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                video_id, title, description, channel, uploader, uploader_id,
                timestamp, release_timestamp, view_count, duration
            ))
            
            # Update tracks.published_date if video exists in tracks table
            upload_date = metadata.get('upload_date', '')
            if upload_date:
                self._update_track_published_date(video_id, upload_date, cursor, job)
            
            conn.commit()
            conn.close()
            job.log_info(f"Successfully saved metadata for video {video_id} to database")
            return True
            
        except Exception as e:
            job.log_exception(e, f"Error saving metadata for video {video_id} to database")
            return False
    
    def _update_track_published_date(self, video_id: str, upload_date: str, cursor, job: Job):
        """Update published_date in tracks table if track exists."""
        try:
            # Convert upload_date (YYYYMMDD) to proper date format
            if len(upload_date) == 8:
                formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                
                cursor.execute("""
                    UPDATE tracks 
                    SET published_date = ? 
                    WHERE video_id = ? AND (published_date IS NULL OR published_date = '')
                """, (formatted_date, video_id))
                
                if cursor.rowcount > 0:
                    job.log_info(f"Updated published_date for track {video_id} to {formatted_date}")
                else:
                    job.log_info(f"No track found with video_id {video_id} or published_date already set")
            else:
                job.log_info(f"Invalid upload_date format for video {video_id}: {upload_date}")
                
        except Exception as e:
            job.log_error(f"Error updating track published_date for video {video_id}: {e}")
    

    
    def get_worker_info(self) -> dict:
        """Return worker information."""
        return {
            'worker_id': self.worker_id,
            'name': 'Single Video Metadata Worker',
            'description': 'Extracts YouTube metadata for individual videos',
            'supported_types': [job_type.value for job_type in self.supported_types],
            'version': '1.0.0',
            'phase': 'Phase 3: Single Video Metadata Worker'
        } 