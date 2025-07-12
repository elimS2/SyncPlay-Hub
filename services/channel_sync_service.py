"""
Channel Sync Service

Service layer for channel synchronization operations.
Provides unified business logic for single channel and group channel synchronization.
"""

import sqlite3
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path

# Database and shared utilities
from controllers.api.shared import get_connection, log_message, get_root_dir, record_event
import database as db


class ChannelSyncService:
    """Service for managing channel synchronization operations."""
    
    def __init__(self):
        """Initialize the Channel Sync Service."""
        self._lock = threading.RLock()
    
    def sync_single_channel_core(
        self,
        channel_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Core business logic for synchronizing a single channel.
        
        Args:
            channel_id: ID of the channel to sync
            date_from: Optional date filter (YYYY-MM-DD)
            date_to: Optional date filter (YYYY-MM-DD)
            
        Returns:
            Dict with sync result: {"status": "started", "message": "...", "job_id": 123}
        """
        try:
            conn = get_connection()
            
            # Get channel info
            channel_raw = db.get_channel_by_id(conn, channel_id)
            if not channel_raw:
                conn.close()
                return {"status": "error", "error": "Channel not found"}
            
            # Convert to dict for easier access
            channel = dict(channel_raw)
            
            # Get group info
            group = db.get_channel_group_by_id(conn, channel['channel_group_id'])
            
            conn.close()
            
            # Use Job Queue System for optimized sync process (same as channel addition)
            try:
                # Import job queue system
                from services.job_queue_service import get_job_queue_service
                from services.job_types import JobType, JobPriority
                from pathlib import Path
                import re
                
                # Get job service
                job_service = get_job_queue_service()
                
                # ✅ IMPORTANT: DO NOT normalize URL - use original URL from database
                # This preserves /videos if user explicitly added it
                channel_url = channel['url']  # Keep original URL as stored
                channel_name = channel['name']
                
                # Helper function to get already downloaded video IDs
                def get_downloaded_video_ids(channel_name: str, group_name: str) -> set:
                    """Get set of video IDs that are already downloaded locally."""
                    try:
                        from download_content import VIDEO_ID_RE
                        root_dir = get_root_dir()
                        if not root_dir:
                            return set()
                        
                        # Try multiple possible folder names (same logic as other functions)
                        possible_folders = []
                        possible_folders.append(root_dir / group_name / f"Channel-{channel_name}")
                        
                        # Also try extracting from URL
                        if '@' in channel_url:
                            url_channel_name = channel_url.split('@')[1].split('/')[0]
                            possible_folders.append(root_dir / group_name / f"Channel-{url_channel_name}")
                        
                        # Find existing folder
                        for folder_path in possible_folders:
                            if folder_path.exists():
                                video_ids = set()
                                for file_path in folder_path.iterdir():
                                    if file_path.is_file():
                                        match = VIDEO_ID_RE.search(file_path.name)
                                        if match:
                                            video_ids.add(match.group(1))
                                
                                log_message(f"[Channel Sync] Found {len(video_ids)} already downloaded videos in {folder_path}")
                                return video_ids
                        
                        log_message(f"[Channel Sync] No existing channel folder found, will download all videos")
                        return set()
                        
                    except Exception as e:
                        log_message(f"[Channel Sync] Error checking downloaded videos: {e}")
                        return set()
                
                # Create callback function to handle metadata completion and create download jobs
                def sync_completion_callback(job_id: int, success: bool, error_message: str = None):
                    """Callback function to create download jobs only for missing videos."""
                    if not success:
                        log_message(f"[Channel Sync] Metadata extraction failed for {channel_url}: {error_message}")
                        return
                    
                    log_message(f"[Channel Sync] Metadata extraction completed for {channel_url}, creating download jobs for missing videos...")
                    
                    # Get already downloaded video IDs
                    downloaded_video_ids = get_downloaded_video_ids(channel_name, group['name'] if group else '')
                    
                    # ✅ IMPORTANT: Also get manually deleted video IDs to avoid re-downloading
                    try:
                        from download_content import get_deleted_video_ids
                        deleted_video_ids = get_deleted_video_ids()
                        log_message(f"[Channel Sync] Found {len(deleted_video_ids)} manually deleted tracks to skip")
                    except Exception as e:
                        log_message(f"[Channel Sync] Warning: Could not get deleted video IDs: {e}")
                        deleted_video_ids = set()
                    
                    # Combine both sets: videos to skip = already downloaded + manually deleted
                    videos_to_skip = downloaded_video_ids | deleted_video_ids
                    log_message(f"[Channel Sync] Total videos to skip: {len(videos_to_skip)} (downloaded: {len(downloaded_video_ids)}, deleted: {len(deleted_video_ids)})")
                    
                    # Get metadata from database and create download jobs
                    try:
                        conn = get_connection()
                        
                        # Get all videos from metadata for this channel
                        cursor = conn.cursor()
                        
                        # Extract channel identifier from URL for metadata search
                        # ✅ IMPORTANT: Use original URL without normalization
                        if '@' in channel_url:
                            channel_name_search = channel_url.split('@')[1].split('/')[0]
                            search_pattern = f'%@{channel_name_search}%'
                        elif '/channel/' in channel_url:
                            channel_id_search = channel_url.split('/channel/')[1].split('/')[0]
                            search_pattern = f'%{channel_id_search}%'
                        elif '/c/' in channel_url:
                            channel_name_search = channel_url.split('/c/')[1].split('/')[0]
                            search_pattern = f'%{channel_name_search}%'
                        else:
                            search_pattern = f'%{channel_url}%'
                        
                        query = """
                            SELECT youtube_id, title FROM youtube_video_metadata 
                            WHERE (channel_url LIKE ? OR channel LIKE ?)
                        """
                        params = [search_pattern, search_pattern]
                        
                        # Add date filter if specified
                        if channel.get('date_from'):  # Use channel's date_from setting
                            try:
                                from datetime import datetime
                                date_obj = datetime.strptime(channel['date_from'], '%Y-%m-%d')
                                timestamp = int(date_obj.timestamp())
                                query += " AND (timestamp >= ? OR release_timestamp >= ?)"
                                params.extend([timestamp, timestamp])
                            except ValueError:
                                log_message(f"[Channel Sync] Invalid channel date_from '{channel['date_from']}', ignoring date filter")
                        
                        query += " ORDER BY timestamp DESC, release_timestamp DESC"
                        
                        cursor.execute(query, params)
                        videos = cursor.fetchall()
                        conn.close()
                        
                        if not videos:
                            log_message(f"[Channel Sync] No videos found in metadata for {channel_url}")
                            return
                        
                        # Create download jobs for each video NOT already downloaded AND NOT manually deleted
                        created_jobs = 0
                        skipped_downloaded = 0
                        skipped_deleted = 0
                        failed_jobs = 0
                        
                        # Calculate target folder for downloads
                        target_folder = f"{group['name']}/Channel-{channel_name}" if group else f"Channel-{channel_name}"
                        
                        for video in videos:
                            video_id = video[0]
                            video_title = video[1] or f"Video {video_id}"
                            
                            # ✅ SKIP if already downloaded (physically present)
                            if video_id in downloaded_video_ids:
                                skipped_downloaded += 1
                                if skipped_downloaded <= 3:  # Log first 3 skipped downloads
                                    log_message(f"[Channel Sync] Skipping already downloaded: {video_title[:50]}...")
                                elif skipped_downloaded == 4:
                                    log_message(f"[Channel Sync] ... (logging truncated, skipping more already downloaded videos)")
                                continue
                            
                            # ✅ SKIP if manually deleted by user
                            if video_id in deleted_video_ids:
                                skipped_deleted += 1
                                if skipped_deleted <= 3:  # Log first 3 skipped deletions
                                    log_message(f"[Channel Sync] Skipping manually deleted: {video_title[:50]}...")
                                elif skipped_deleted == 4:
                                    log_message(f"[Channel Sync] ... (logging truncated, skipping more manually deleted videos)")
                                continue
                            
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            
                            try:
                                # Create single video download job
                                job_id = job_service.create_and_add_job(
                                    JobType.SINGLE_VIDEO_DOWNLOAD,
                                    priority=JobPriority.NORMAL,
                                    playlist_url=video_url,
                                    target_folder=target_folder,
                                    format_selector='bestvideo+bestaudio/best',
                                    extract_audio=False,  # Download video files for channels
                                    download_archive=True,
                                    exclude_shorts=True  # Exclude YouTube Shorts
                                )
                                
                                created_jobs += 1
                                if created_jobs <= 5:  # Log first 5 jobs created
                                    log_message(f"[Channel Sync] Queued download job #{job_id} for missing video: {video_title[:50]}...")
                                elif created_jobs == 6:
                                    log_message(f"[Channel Sync] ... (logging truncated, continuing to queue remaining missing videos)")
                                
                            except Exception as e:
                                failed_jobs += 1
                                log_message(f"[Channel Sync] Failed to create download job for video {video_id}: {e}")
                        
                        # Enhanced summary with breakdown
                        log_message(f"[Channel Sync] Channel sync setup completed:")
                        log_message(f"[Channel Sync]   - New download jobs created: {created_jobs}")
                        log_message(f"[Channel Sync]   - Already downloaded (skipped): {skipped_downloaded}")
                        log_message(f"[Channel Sync]   - Manually deleted (skipped): {skipped_deleted}")
                        log_message(f"[Channel Sync]   - Failed to create: {failed_jobs}")
                        log_message(f"[Channel Sync]   - Total videos in metadata: {len(videos)}")
                        
                        # Update channel sync timestamp
                        try:
                            conn = get_connection()
                            # Count total files (already downloaded + will be downloaded)
                            # Note: We don't count deleted videos as they shouldn't be included in track count
                            total_expected_tracks = len(downloaded_video_ids) + created_jobs
                            db.update_channel_sync(conn, channel_id, total_expected_tracks)
                            conn.close()
                            log_message(f"[Channel Sync] Updated channel sync timestamp with {total_expected_tracks} expected tracks (excluding deleted)")
                        except Exception as e:
                            log_message(f"[Channel Sync] Warning: Failed to update sync timestamp: {e}")
                        
                    except Exception as e:
                        log_message(f"[Channel Sync] Error creating download jobs: {e}")
                
                # Step 1: Create metadata extraction job (to update metadata first)
                metadata_job_id = job_service.create_and_add_job(
                    JobType.METADATA_EXTRACTION,
                    callback=sync_completion_callback,
                    priority=JobPriority.HIGH,
                    channel_url=channel_url,  # ✅ Use original URL without normalization
                    channel_id=channel_id,
                    force_update=False  # Don't force update during sync
                )
                
                log_message(f"[Channels] Started sync for channel: {channel['name']}")
                log_message(f"[Channels] Created metadata extraction job #{metadata_job_id}")
                log_message(f"[Channels] Download jobs will be created automatically for missing videos only")
                log_message(f"[Channels] URL preserved as stored: {channel_url}")
                
                return {
                    "status": "started", 
                    "channel_id": channel_id,
                    "metadata_job_id": metadata_job_id,
                    "message": f"Channel sync started for '{channel['name']}'. Optimized sync process - updating metadata first, then downloading missing videos only.",
                    "process": "optimized_sync",
                    "channel_url": channel_url,
                    "channel_name": channel['name'],
                    "url_preserved": True,  # Indicate that URL was not normalized
                    "steps": [
                        "1. Update channel metadata (in progress)",
                        "2. Check for already downloaded videos (pending)", 
                        "3. Download missing videos only (pending)"
                    ],
                    "date_filter": {"from": date_from, "to": date_to} if date_from or date_to else None
                }
                
            except ImportError:
                # Fallback to old system if job queue not available
                log_message(f"[Channels] Job Queue System not available, falling back to direct download")
                
                # Start background sync (original code as fallback)
                def _sync_worker():
                    try:
                        from download_content import download_content
                        
                        # Set up progress callback for logging
                        def progress_callback(msg):
                            log_message(f"[Channel Sync] {channel['name']}: {msg}")
                        
                        # ✅ IMPORTANT: DO NOT normalize URL - pass original URL 
                        # We need to modify download_content to accept a flag to skip normalization
                        root_dir = get_root_dir()
                        if not root_dir:
                            log_message(f"[Channel Sync] Error: ROOT_DIR not initialized")
                            return
                            
                        download_content(
                            url=channel['url'],  # ✅ Use original URL from database
                            output_dir=root_dir,
                            audio_only=False,  # Download video files for channels
                            sync=True,
                            channel_group=group['name'] if group else None,
                            date_from=date_from,
                            exclude_shorts=True,  # Exclude Shorts from download
                            progress_callback=progress_callback,
                            skip_url_normalization=True  # ✅ Preserve /videos for channel sync
                        )
                        
                        # Update channel sync timestamp - count actual tracks
                        conn = get_connection()
                        
                        # Count actual files in channel folder
                        channel_folder = root_dir / (group['name'] if group else '') / f"Channel-{channel['name']}"
                        actual_track_count = 0
                        if channel_folder.exists():
                            video_extensions = ['.mp4', '.webm', '.mkv', '.avi']
                            actual_track_count = len([f for f in channel_folder.iterdir() 
                                                    if f.is_file() and f.suffix.lower() in video_extensions])
                        
                        db.update_channel_sync(conn, channel_id, actual_track_count)
                        conn.close()
                        
                        log_message(f"[Channel Sync] Successfully synced channel: {channel['name']}")
                        
                    except Exception as e:
                        log_message(f"[Channel Sync] Error syncing channel {channel['name']}: {e}")
                
                # Start sync in background
                import threading
                sync_thread = threading.Thread(target=_sync_worker, daemon=True)
                sync_thread.start()
                
                return {
                    "status": "started", 
                    "message": f"Sync started for channel '{channel['name']}' (fallback method)",
                    "channel_url": channel['url'],
                    "channel_name": channel['name'],
                    "process": "fallback",
                    "date_filter": {"from": date_from, "to": date_to} if date_from or date_to else None
                }
            except Exception as e:
                log_message(f"[Channels] Error during channel sync: {e}")
                return {"status": "error", "error": str(e)}
                
        except Exception as e:
            log_message(f"[Channels] Error syncing channel: {e}")
            return {"status": "error", "error": str(e)}
    
    def sync_channel_group(
        self,
        group_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synchronize all channels in a group.
        
        Args:
            group_id: ID of the channel group to sync
            date_from: Optional date filter (YYYY-MM-DD)
            date_to: Optional date filter (YYYY-MM-DD)
            
        Returns:
            Dict with sync result: {"status": "started", "channels": 5, "results": [...]}
        """
        # TODO: This will be implemented in Step 2.1
        # Will iterate through channels and call sync_single_channel_core for each
        pass
    
    def quick_sync_channel_group(
        self,
        group_id: int
    ) -> Dict[str, Any]:
        """
        Quick sync all channels in a group.
        
        Creates QUICK_SYNC jobs for all channels in the group. Each job will process
        channels individually with optimized metadata fetching.
        
        Args:
            group_id: ID of the channel group to quick sync
            
        Returns:
            Dict with sync result: {"status": "started", "message": "...", "jobs_created": 5}
        """
        try:
            conn = get_connection()
            
            # Get group info
            group_raw = db.get_channel_group_by_id(conn, group_id)
            if not group_raw:
                conn.close()
                return {"status": "error", "error": "Channel group not found"}
            
            group = dict(group_raw)
            
            # Get channels in group
            channels_raw = db.get_channels_by_group(conn, group_id)
            if not channels_raw:
                conn.close()
                return {"status": "error", "error": "No channels found in group"}
            
            channels = [dict(channel) for channel in channels_raw]
            conn.close()
            
            log_message(f"[Quick Sync Group] Starting quick sync for group: {group['name']}")
            log_message(f"[Quick Sync Group] Found {len(channels)} channels to process")
            
            # Create quick sync jobs for all channels
            try:
                from services.job_queue_service import get_job_queue_service
                from services.job_types import JobType, JobPriority
                
                job_service = get_job_queue_service()
                
                created_jobs = []
                failed_jobs = 0
                
                for channel in channels:
                    try:
                        # Create quick sync job with high priority
                        job_id = job_service.create_and_add_job(
                            JobType.QUICK_SYNC,
                            priority=JobPriority.HIGH,
                            channel_id=channel['id'],
                            channel_name=channel['name'],
                            channel_url=channel['url'],
                            group_name=group['name']
                        )
                        
                        created_jobs.append({
                            'job_id': job_id,
                            'channel_id': channel['id'],
                            'channel_name': channel['name']
                        })
                        
                        log_message(f"[Quick Sync Group] Created job #{job_id} for channel: {channel['name']}")
                        
                    except Exception as e:
                        failed_jobs += 1
                        log_message(f"[Quick Sync Group] Failed to create job for channel {channel['name']}: {e}")
                
                log_message(f"[Quick Sync Group] Quick sync group completed:")
                log_message(f"[Quick Sync Group]   - Jobs created: {len(created_jobs)}")
                log_message(f"[Quick Sync Group]   - Failed to create: {failed_jobs}")
                
                return {
                    "status": "started",
                    "message": f"Quick sync started for {len(created_jobs)} channels in group '{group['name']}'",
                    "group_name": group['name'],
                    "group_id": group_id,
                    "channels_count": len(channels),
                    "jobs_created": len(created_jobs),
                    "failed_jobs": failed_jobs,
                    "created_jobs": created_jobs,
                    "process": "quick_sync_group_queued"
                }
                
            except ImportError:
                # Fallback if job queue not available
                log_message(f"[Quick Sync Group] Job Queue System not available, falling back to sequential execution")
                
                # Sequential execution as fallback
                def _group_sync_worker():
                    try:
                        success_count = 0
                        failed_count = 0
                        
                        for channel in channels:
                            try:
                                # Execute quick sync directly for each channel
                                result = self.quick_sync_channel_core(channel['id'])
                                
                                if result.get('status') in ['started', 'up_to_date']:
                                    success_count += 1
                                    if result.get('status') == 'started':
                                        log_message(f"[Quick Sync Group] Channel {channel['name']}: {result.get('new_videos', 0)} new videos")
                                    else:
                                        log_message(f"[Quick Sync Group] Channel {channel['name']}: up to date")
                                else:
                                    failed_count += 1
                                    log_message(f"[Quick Sync Group] Channel {channel['name']} failed: {result.get('error', 'Unknown error')}")
                                    
                            except Exception as e:
                                failed_count += 1
                                log_message(f"[Quick Sync Group] Error quick syncing channel {channel['name']}: {e}")
                        
                        log_message(f"[Quick Sync Group] Completed group '{group['name']}': {success_count} channels processed, {failed_count} failed")
                        
                    except Exception as e:
                        log_message(f"[Quick Sync Group] Error quick syncing group '{group['name']}': {e}")
                
                # Start sync in background
                import threading
                sync_thread = threading.Thread(target=_group_sync_worker, daemon=True)
                sync_thread.start()
                
                return {
                    "status": "started",
                    "message": f"Quick sync started for {len(channels)} channels in group '{group['name']}' (fallback method)",
                    "group_name": group['name'],
                    "group_id": group_id,
                    "channels_count": len(channels),
                    "process": "quick_sync_group_fallback"
                }
                
        except Exception as e:
            log_message(f"[Quick Sync Group] Error quick syncing channel group: {e}")
            return {"status": "error", "error": str(e)}
    
    def quick_sync_channel_core(
        self,
        channel_id: int
    ) -> Dict[str, Any]:
        """
        Quick sync logic for a single channel.
        
        Fetches metadata directly from YouTube starting from the newest videos,
        and stops when it reaches already downloaded content. This is much more
        efficient than full metadata extraction.
        
        Args:
            channel_id: ID of the channel to quick sync
            
        Returns:
            Dict with sync result: {"status": "started", "message": "...", "new_videos": 5}
        """
        try:
            conn = get_connection()
            
            # Get channel info
            channel_raw = db.get_channel_by_id(conn, channel_id)
            if not channel_raw:
                conn.close()
                return {"status": "error", "error": "Channel not found"}
            
            channel = dict(channel_raw)
            
            # Get group info
            group_raw = db.get_channel_group_by_id(conn, channel['channel_group_id'])
            group = dict(group_raw) if group_raw else None
            
            conn.close()
            
            log_message(f"[Quick Sync] Starting quick sync for channel: {channel['name']}")
            log_message(f"[Quick Sync] Channel URL: {channel['url']}")
            
            # Step 1: Get latest videos metadata directly from YouTube in batches
            try:
                from utils.cookies_manager import get_cookies_for_download
                from yt_dlp import YoutubeDL
                
                # Get cookies configuration
                cookies_path, use_browser = get_cookies_for_download(None, False)
                
                # Setup yt-dlp options for metadata extraction
                common_cookies = ({"cookiefile": cookies_path} if cookies_path else {})
                if use_browser and not cookies_path:
                    common_cookies.setdefault("cookiesfrombrowser", ("chrome",))
                
                # Configure yt-dlp for quick metadata extraction
                ydl_opts = {
                    "quiet": True,
                    "skip_download": True,
                    "extract_flat": False,  # We need full metadata for dates
                    "ignoreerrors": True,
                    **common_cookies
                }
                
                new_videos_to_download = []
                batch_size = 5  # Very small batch for ultra-fast detection of already downloaded videos
                current_batch = 1
                found_downloaded_video = False
                
                log_message(f"[Quick Sync] Fetching metadata in batches of {batch_size} videos...")
                
                while not found_downloaded_video and current_batch <= 60:  # Limit to 60 batches (300 videos max)
                    start_index = (current_batch - 1) * batch_size + 1
                    end_index = current_batch * batch_size
                    
                    log_message(f"[Quick Sync] Processing batch {current_batch}: videos {start_index}-{end_index}")
                    
                    # Set playlist items for this batch
                    ydl_opts["playlist_items"] = f"{start_index}:{end_index}"
                    
                    try:
                        with YoutubeDL(ydl_opts) as ydl:
                            # Extract metadata for this batch
                            info = ydl.extract_info(channel['url'], download=False)
                            
                            if not info or 'entries' not in info:
                                log_message(f"[Quick Sync] No videos found in batch {current_batch}")
                                break
                            
                            entries = info.get('entries', [])
                            if not entries:
                                log_message(f"[Quick Sync] Empty batch {current_batch}, stopping")
                                break
                            
                            log_message(f"[Quick Sync] Found {len(entries)} videos in batch {current_batch}")
                            
                            # Process each video in this batch
                            for entry in entries:
                                if not entry:  # Skip None entries
                                    continue
                                    
                                video_id = entry.get('id')
                                if not video_id:
                                    continue
                                
                                video_title = entry.get('title', f'Video {video_id}')
                                
                                # Check if this video is already downloaded
                                conn = get_connection()
                                if db.is_track_already_downloaded(conn, video_id):
                                    log_message(f"[Quick Sync] Found already downloaded video: {video_title[:50]}...")
                                    log_message(f"[Quick Sync] Stopping here - reached already downloaded content")
                                    conn.close()
                                    found_downloaded_video = True
                                    break
                                conn.close()
                                
                                # Check if video is available for download
                                availability = entry.get('availability', 'public')
                                if availability in ['private', 'premium_only', 'subscriber_only']:
                                    log_message(f"[Quick Sync] Skipping unavailable video: {video_title[:50]}... ({availability})")
                                    continue
                                
                                # Check if it's a short (duration < 60 seconds)
                                duration = entry.get('duration')
                                if duration and duration < 60:
                                    log_message(f"[Quick Sync] Skipping short video: {video_title[:50]}... ({duration}s)")
                                    continue
                                
                                # Check if it's a live stream
                                live_status = entry.get('live_status')
                                if live_status in ['is_live', 'is_upcoming']:
                                    log_message(f"[Quick Sync] Skipping live/upcoming video: {video_title[:50]}... ({live_status})")
                                    continue
                                
                                # Get publication date
                                timestamp = entry.get('timestamp') or entry.get('release_timestamp')
                                pub_date = None
                                if timestamp:
                                    try:
                                        from datetime import datetime
                                        pub_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                                    except (ValueError, OSError):
                                        pass
                                
                                # This video should be downloaded
                                new_videos_to_download.append({
                                    'video_id': video_id,
                                    'title': video_title,
                                    'pub_date': pub_date,
                                    'duration': duration,
                                    'availability': availability
                                })
                                
                                # Save metadata to database for later use by scan_to_db.py
                                try:
                                    from utils.metadata_utils import save_video_metadata_from_entry
                                    
                                    # Save metadata using common utility function
                                    success = save_video_metadata_from_entry(
                                        entry=entry,
                                        channel_url=channel['url'],  # Use original channel URL
                                        logger_func=lambda msg: log_message(f"[Quick Sync] {msg}")
                                    )
                                    
                                    if success:
                                        log_message(f"[Quick Sync] Saved metadata for: {video_title[:50]}...")
                                    else:
                                        log_message(f"[Quick Sync] Warning: Failed to save metadata for {video_id}")
                                        
                                except Exception as e:
                                    log_message(f"[Quick Sync] Warning: Failed to save metadata for {video_id}: {e}")
                                
                                log_message(f"[Quick Sync] Will download: {video_title[:50]}... ({pub_date or 'unknown date'})")
                    
                    except Exception as e:
                        log_message(f"[Quick Sync] Error processing batch {current_batch}: {e}")
                        break
                    
                    current_batch += 1
                
                log_message(f"[Quick Sync] Metadata extraction completed. Found {len(new_videos_to_download)} new videos to download.")
                
                if not new_videos_to_download:
                    return {
                        "status": "up_to_date",
                        "message": f"Channel '{channel['name']}' is up to date. No new videos to download.",
                        "channel_name": channel['name'],
                        "batches_processed": current_batch - 1,
                        "new_videos": 0
                    }
                
                # Step 2: Create download jobs for new videos
                try:
                    from services.job_queue_service import get_job_queue_service
                    from services.job_types import JobType, JobPriority
                    
                    job_service = get_job_queue_service()
                    
                    # Calculate target folder for downloads
                    target_folder = f"{group['name']}/Channel-{channel['name']}" if group else f"Channel-{channel['name']}"
                    
                    created_jobs = 0
                    failed_jobs = 0
                    
                    for video in new_videos_to_download:
                        video_id = video['video_id']
                        video_title = video['title']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        try:
                            # Create single video download job
                            job_id = job_service.create_and_add_job(
                                JobType.SINGLE_VIDEO_DOWNLOAD,
                                priority=JobPriority.HIGH,  # High priority for quick sync
                                playlist_url=video_url,
                                target_folder=target_folder,
                                format_selector='bestvideo+bestaudio/best',
                                extract_audio=False,  # Download video files for channels
                                download_archive=True,
                                exclude_shorts=True
                            )
                            
                            created_jobs += 1
                            if created_jobs <= 5:  # Log first 5 jobs
                                log_message(f"[Quick Sync] Queued job #{job_id} for: {video_title[:50]}...")
                            elif created_jobs == 6:
                                log_message(f"[Quick Sync] ... (logging truncated, continuing to queue remaining videos)")
                            
                        except Exception as e:
                            failed_jobs += 1
                            log_message(f"[Quick Sync] Failed to create job for {video_id}: {e}")
                    
                    log_message(f"[Quick Sync] Quick sync completed:")
                    log_message(f"[Quick Sync]   - Channel: {channel['name']}")
                    log_message(f"[Quick Sync]   - Batches processed: {current_batch - 1}")
                    log_message(f"[Quick Sync]   - New videos found: {len(new_videos_to_download)}")
                    log_message(f"[Quick Sync]   - Download jobs created: {created_jobs}")
                    log_message(f"[Quick Sync]   - Failed jobs: {failed_jobs}")
                    
                    return {
                        "status": "started",
                        "message": f"Quick sync started for channel '{channel['name']}'. Found {len(new_videos_to_download)} new videos to download.",
                        "channel_name": channel['name'],
                        "channel_id": channel_id,
                        "new_videos": len(new_videos_to_download),
                        "jobs_created": created_jobs,
                        "jobs_failed": failed_jobs,
                        "batches_processed": current_batch - 1,
                        "process": "quick_sync_optimized"
                    }
                    
                except ImportError:
                    # Fallback if job queue not available
                    log_message(f"[Quick Sync] Job Queue System not available, quick sync requires job queue")
                    return {
                        "status": "error",
                        "error": "Quick sync requires job queue system which is not available"
                    }
                
            except ImportError:
                log_message(f"[Quick Sync] yt-dlp not available, cannot perform quick sync")
                return {
                    "status": "error",
                    "error": "Quick sync requires yt-dlp which is not available"
                }
                
        except Exception as e:
            log_message(f"[Quick Sync] Error during quick sync: {e}")
            return {"status": "error", "error": str(e)}


# Singleton instance
_channel_sync_service: Optional[ChannelSyncService] = None


def get_channel_sync_service() -> ChannelSyncService:
    """Get singleton instance of channel sync service."""
    global _channel_sync_service
    
    if _channel_sync_service is None:
        _channel_sync_service = ChannelSyncService()
    
    return _channel_sync_service 