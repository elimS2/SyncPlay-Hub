"""Channels API endpoints."""

import re
import threading
import shutil
import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event
import database as db

# Create blueprint
channels_bp = Blueprint('channels', __name__)

@channels_bp.route("/channel_groups")
def api_get_channel_groups():
    """Get all channel groups with statistics."""
    try:
        conn = get_connection()
        groups = db.get_channel_groups(conn)
        conn.close()
        
        log_message(f"[Channels] Retrieved {len(groups)} channel groups")
        return jsonify({"status": "ok", "groups": groups})
        
    except Exception as e:
        log_message(f"[Channels] Error retrieving channel groups: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/channels/<int:group_id>")
def api_get_channels_by_group(group_id: int):
    """Get all channels in a specific group."""
    try:
        conn = get_connection()
        channels_raw = db.get_channels_by_group(conn, group_id)
        conn.close()
        
        # Convert sqlite3.Row objects to dictionaries
        channels = [dict(channel) for channel in channels_raw]
        
        log_message(f"[Channels] Retrieved {len(channels)} channels for group {group_id}")
        return jsonify({"status": "ok", "channels": channels})
        
    except Exception as e:
        log_message(f"[Channels] Error retrieving channels for group {group_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/create_channel_group", methods=["POST"])
def api_create_channel_group():
    """Create a new channel group."""
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        behavior_type = data.get('behavior_type', 'music')
        auto_delete_enabled = data.get('auto_delete_enabled', False)
        play_order = data.get('play_order', 'random')
        
        # Validate required fields
        if not name:
            return jsonify({"status": "error", "error": "Group name is required"}), 400
        
        # Validate behavior type
        valid_behaviors = ['music', 'news', 'education', 'podcasts']
        if behavior_type not in valid_behaviors:
            return jsonify({"status": "error", "error": f"Invalid behavior type. Must be one of: {valid_behaviors}"}), 400
        
        # Validate play order
        valid_orders = ['random', 'newest_first', 'oldest_first']
        if play_order not in valid_orders:
            return jsonify({"status": "error", "error": f"Invalid play order. Must be one of: {valid_orders}"}), 400
        
        # Create group
        conn = get_connection()
        group_id = db.create_channel_group(
            conn, 
            name=name,
            behavior_type=behavior_type,
            auto_delete_enabled=auto_delete_enabled,
            play_order=play_order
        )
        conn.close()
        
        log_message(f"[Channels] Created channel group: {name} (ID: {group_id}, type: {behavior_type})")
        return jsonify({"status": "ok", "group_id": group_id, "message": f"Channel group '{name}' created successfully"})
        
    except Exception as e:
        log_message(f"[Channels] Error creating channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/delete_channel_group/<int:group_id>", methods=["POST"])
def api_delete_channel_group(group_id: int):
    """Delete an empty channel group."""
    try:
        conn = get_connection()
        
        # Get group info before deletion
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        group_name = group['name']
        
        # Attempt to delete the group (will fail if it has channels)
        deleted = db.delete_channel_group(conn, group_id)
        conn.close()
        
        if deleted:
            log_message(f"[Channels] Deleted empty channel group: {group_name} (ID: {group_id})")
            return jsonify({
                "status": "success",
                "message": f"Empty channel group '{group_name}' deleted successfully"
            })
        else:
            return jsonify({
                "status": "error", 
                "error": "Cannot delete channel group - it still contains channels"
            }), 400
            
    except Exception as e:
        log_message(f"[Channels] Error deleting channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/add_channel", methods=["POST"])
def api_add_channel():
    """Add a YouTube channel to a group and start optimized download process."""
    try:
        data = request.get_json() or {}
        group_id = data.get('group_id')
        channel_url = data.get('url', '').strip()  # Accept 'url' parameter
        date_from = data.get('date_from')  # Optional date filter
        
        # Validate required fields
        if not group_id:
            return jsonify({"status": "error", "error": "Group ID is required"}), 400
        
        if not channel_url:
            return jsonify({"status": "error", "error": "Channel URL is required"}), 400
        
        # Validate YouTube channel URL format
        channel_patterns = [
            r'youtube\.com/@([^/\s]+)(?:/videos)?',  # @ChannelName or @ChannelName/videos format
            r'youtube\.com/c/([^/\s]+)',  # /c/ChannelName format
            r'youtube\.com/channel/([^/\s]+)',  # /channel/ChannelID format
            r'youtube\.com/user/([^/\s]+)'  # /user/Username format
        ]
        
        valid_url = False
        for pattern in channel_patterns:
            if re.search(pattern, channel_url):
                valid_url = True
                break
        
        if not valid_url:
            return jsonify({
                "status": "error", 
                "error": "Invalid YouTube channel URL. Supported formats: @ChannelName, /c/ChannelName, /channel/ChannelID, /user/Username"
            }), 400
        
        # Check if channel already exists
        conn = get_connection()
        existing_channel = db.get_channel_by_url(conn, channel_url)
        if existing_channel:
            conn.close()
            return jsonify({
                "status": "error", 
                "error": f"Channel already exists in group '{existing_channel['group_name']}'"
            }), 400
        
        # Get group info
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Extract channel name from URL for display
        channel_name = "Unknown Channel"
        name_match = re.search(r'@([^/\s]+)', channel_url)
        if name_match:
            channel_name = name_match.group(1)
        else:
            # Try other patterns
            for pattern in [r'/c/([^/\s]+)', r'/channel/([^/\s]+)', r'/user/([^/\s]+)']:
                match = re.search(pattern, channel_url)
                if match:
                    channel_name = match.group(1)
                    break
        
        # Create channel entry
        channel_id = db.create_channel(conn, channel_name, channel_url, group_id, date_from)
        
        # Record channel addition event
        db.record_channel_added(conn, channel_url, channel_name, group['name'])
        
        conn.close()
        
        # Use Job Queue System for optimized download process
        try:
            # Import job queue system
            from services.job_queue_service import get_job_queue_service
            from services.job_types import JobType, JobPriority
            
            # Get job service
            job_service = get_job_queue_service()
            
            # Create callback function to handle metadata completion and create download jobs
            def metadata_completion_callback(job_id: int, success: bool, error_message: str = None):
                """Callback function to create download jobs after metadata extraction."""
                if not success:
                    log_message(f"[Channel Add] Metadata extraction failed for {channel_url}: {error_message}")
                    return
                
                log_message(f"[Channel Add] Metadata extraction completed for {channel_url}, creating download jobs...")
                
                # Get metadata from database and create download jobs
                try:
                    conn = get_connection()
                    
                    # Get all videos from metadata for this channel
                    cursor = conn.cursor()
                    
                    # Extract channel identifier from URL for metadata search
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
                    if date_from:
                        try:
                            from datetime import datetime
                            date_obj = datetime.strptime(date_from, '%Y-%m-%d')
                            timestamp = int(date_obj.timestamp())
                            query += " AND (timestamp >= ? OR release_timestamp >= ?)"
                            params.extend([timestamp, timestamp])
                        except ValueError:
                            log_message(f"[Channel Add] Invalid date format '{date_from}', ignoring date filter")
                    
                    query += " ORDER BY timestamp DESC, release_timestamp DESC"
                    
                    cursor.execute(query, params)
                    videos = cursor.fetchall()
                    conn.close()
                    
                    if not videos:
                        log_message(f"[Channel Add] No videos found in metadata for {channel_url}")
                        return
                    
                    # Create download jobs for each video
                    created_jobs = 0
                    failed_jobs = 0
                    
                    # Calculate target folder for downloads
                    target_folder = f"{group['name']}/Channel-{channel_name}"
                    
                    for video in videos:
                        video_id = video[0]
                        video_title = video[1] or f"Video {video_id}"
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
                                log_message(f"[Channel Add] Queued download job #{job_id} for video: {video_title[:50]}...")
                            elif created_jobs == 6:
                                log_message(f"[Channel Add] ... (logging truncated, continuing to queue remaining videos)")
                            
                        except Exception as e:
                            failed_jobs += 1
                            log_message(f"[Channel Add] Failed to create download job for video {video_id}: {e}")
                    
                    log_message(f"[Channel Add] Channel download setup completed: {created_jobs} download jobs created, {failed_jobs} failed")
                    
                except Exception as e:
                    log_message(f"[Channel Add] Error creating download jobs: {e}")
            
            # Step 1: Create metadata extraction job
            metadata_job_id = job_service.create_and_add_job(
                JobType.METADATA_EXTRACTION,
                callback=metadata_completion_callback,
                priority=JobPriority.HIGH,
                channel_url=channel_url,
                channel_id=channel_id,
                force_update=False
            )
            
            log_message(f"[Channels] Added channel to group '{group['name']}': {channel_url}")
            log_message(f"[Channels] Created metadata extraction job #{metadata_job_id}")
            log_message(f"[Channels] Download jobs will be created automatically after metadata extraction")
            
            return jsonify({
                "status": "started", 
                "channel_id": channel_id,
                "metadata_job_id": metadata_job_id,
                "message": f"Channel added to group '{group['name']}'. Optimized download process started - extracting metadata first, then downloading videos.",
                "process": "optimized",
                "steps": [
                    "1. Extract channel metadata (in progress)",
                    "2. Create individual video download jobs (pending)",
                    "3. Download videos in queue (pending)"
                ]
            })
            
        except ImportError:
            # Fallback to old system if job queue not available
            log_message(f"[Channels] Job Queue System not available, falling back to direct download")
            
            # Start background download (original code as fallback)
            def _download_worker():
                try:
                    # Import download_content from new module
                    from download_content import download_content
                    
                    # Set up progress callback for logging
                    def progress_callback(msg):
                        log_message(f"[Channel Download] {msg}")
                    
                    # Get root directory
                    root_dir = get_root_dir()
                    if not root_dir:
                        log_message(f"[Channel Download] Error: ROOT_DIR not initialized")
                        return
                    
                    download_content(
                        url=channel_url,
                        output_dir=root_dir,
                        audio_only=False,  # Download video files for channels
                        sync=True,
                        channel_group=group['name'],
                        date_from=date_from,
                        exclude_shorts=True,  # Exclude Shorts from download
                        progress_callback=progress_callback
                    )
                    
                    # Update channel sync timestamp
                    conn = get_connection()
                    actual_track_count = 0  # Will be updated by scan
                    db.update_channel_sync(conn, channel_id, actual_track_count)
                    conn.close()
                    
                    log_message(f"[Channels] Channel download complete via fallback method")
                    
                except Exception as e:
                    log_message(f"[Channels] Error downloading channel {channel_url}: {e}")
            
            # Start download in background
            import threading
            download_thread = threading.Thread(target=_download_worker, daemon=True)
            download_thread.start()
            
            return jsonify({
                "status": "started", 
                "channel_id": channel_id, 
                "message": f"Channel added to group '{group['name']}' and download started in background (fallback mode)"
            })
            
    except Exception as e:
        log_message(f"[Channels] Error adding channel: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/sync_channel_group/<int:group_id>", methods=["POST"])
def api_sync_channel_group(group_id: int):
    """Sync all channels in a group."""
    try:
        data = request.get_json() or {}
        date_from = data.get('date_from')  # Optional date filter
        date_to = data.get('date_to')  # Optional date filter
        
        conn = get_connection()
        
        # Get group info
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Get channels in group
        channels_raw = db.get_channels_by_group(conn, group_id)
        if not channels_raw:
            conn.close()
            return jsonify({"status": "error", "error": "No channels found in group"}), 400
        
        # Convert sqlite3.Row objects to dictionaries
        channels = [dict(channel) for channel in channels_raw]
        
        conn.close()
        
        # Start background sync for all channels
        def _sync_worker():
            try:
                from download_content import download_content
                
                success_count = 0
                for channel in channels:
                    try:
                        # Set up progress callback for logging
                        def progress_callback(msg):
                            log_message(f"[Group Sync] {channel['name']}: {msg}")
                        
                        # Sync channel content
                        root_dir = get_root_dir()
                        if not root_dir:
                            log_message(f"[Group Sync] Error: ROOT_DIR not initialized")
                            return
                            
                        download_content(
                            url=channel['url'],
                            output_dir=root_dir,
                            audio_only=False,  # Download video files for channels
                            sync=True,
                            channel_group=group['name'],
                            date_from=date_from,
                            exclude_shorts=True,  # Exclude Shorts from download
                            progress_callback=progress_callback
                        )
                        
                        # Update channel sync timestamp - count actual tracks
                        conn = get_connection()
                        
                        # Count actual files in channel folder
                        channel_folder = root_dir / group['name'] / f"Channel-{channel['name']}"
                        actual_track_count = 0
                        if channel_folder.exists():
                            video_extensions = ['.mp4', '.webm', '.mkv', '.avi']
                            actual_track_count = len([f for f in channel_folder.iterdir() 
                                                    if f.is_file() and f.suffix.lower() in video_extensions])
                        
                        db.update_channel_sync(conn, channel['id'], actual_track_count)
                        conn.close()
                        
                        success_count += 1
                        log_message(f"[Group Sync] Successfully synced channel: {channel['name']}")
                        
                    except Exception as e:
                        log_message(f"[Group Sync] Error syncing channel {channel['name']}: {e}")
                
                log_message(f"[Group Sync] Completed group '{group['name']}': {success_count}/{len(channels)} channels synced")
                
            except Exception as e:
                log_message(f"[Group Sync] Error syncing group '{group['name']}': {e}")
        
        # Start sync in background
        sync_thread = threading.Thread(target=_sync_worker, daemon=True)
        sync_thread.start()
        
        log_message(f"[Channels] Started sync for group '{group['name']}' with {len(channels)} channels")
        
        return jsonify({
            "status": "started", 
            "message": f"Sync started for {len(channels)} channels in group '{group['name']}'",
            "group_name": group['name'],
            "channels_count": len(channels),
            "date_filter": {"from": date_from, "to": date_to} if date_from or date_to else None
        })
        
    except Exception as e:
        log_message(f"[Channels] Error syncing channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/sync_channel/<int:channel_id>", methods=["POST"])
def api_sync_channel(channel_id: int):
    """Sync individual channel."""
    try:
        data = request.get_json() or {}
        date_from = data.get('date_from')  # Optional date filter
        date_to = data.get('date_to')  # Optional date filter
        
        conn = get_connection()
        
        # Get channel info
        channel_raw = db.get_channel_by_id(conn, channel_id)
        if not channel_raw:
            conn.close()
            return jsonify({"status": "error", "error": "Channel not found"}), 404
        
        # Convert to dict for easier access
        channel = dict(channel_raw)
        
        # Get group info
        group = db.get_channel_group_by_id(conn, channel['channel_group_id'])
        
        conn.close()
        
        # Start background sync
        def _sync_worker():
            try:
                from download_content import download_content
                
                # Set up progress callback for logging
                def progress_callback(msg):
                    log_message(f"[Channel Sync] {channel['name']}: {msg}")
                
                # Sync channel content
                root_dir = get_root_dir()
                if not root_dir:
                    log_message(f"[Channel Sync] Error: ROOT_DIR not initialized")
                    return
                    
                download_content(
                    url=channel['url'],
                    output_dir=root_dir,
                    audio_only=False,  # Download video files for channels
                    sync=True,
                    channel_group=group['name'] if group else None,
                    date_from=date_from,
                    exclude_shorts=True,  # Exclude Shorts from download
                    progress_callback=progress_callback
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
        sync_thread = threading.Thread(target=_sync_worker, daemon=True)
        sync_thread.start()
        
        log_message(f"[Channels] Started sync for channel: {channel['name']}")
        
        return jsonify({
            "status": "started", 
            "message": f"Sync started for channel '{channel['name']}'",
            "channel_url": channel['url'],
            "channel_name": channel['name'],
            "date_filter": {"from": date_from, "to": date_to} if date_from or date_to else None
        })
        
    except Exception as e:
        log_message(f"[Channels] Error syncing channel: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/refresh_channel_stats/<int:channel_id>", methods=["POST"])
def api_refresh_channel_stats(channel_id: int):
    """Refresh channel statistics by counting actual files."""
    try:
        conn = get_connection()
        
        # Get channel info
        channel_raw = db.get_channel_by_id(conn, channel_id)
        if not channel_raw:
            conn.close()
            return jsonify({"status": "error", "error": "Channel not found"}), 404
        
        channel = dict(channel_raw)
        
        # Get group info
        group = db.get_channel_group_by_id(conn, channel['channel_group_id'])
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Count actual files in channel folder
        # Try multiple possible folder names for the channel
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
            
        possible_folders = []
        
        # 1. Try full channel name
        possible_folders.append(root_dir / group['name'] / f"Channel-{channel['name']}")
        
        # 2. Try extracting channel name from URL
        url = channel['url']
        if '@' in url:
            # Extract from URL like https://www.youtube.com/@LAUDenjoy/videos
            url_channel_name = url.split('@')[1].split('/')[0]
            possible_folders.append(root_dir / group['name'] / f"Channel-{url_channel_name}")
        
        # 3. Try short name (remove common suffixes)
        short_name = channel['name'].replace('enjoy', '').replace('music', '').replace('official', '').strip()
        if short_name != channel['name']:
            possible_folders.append(root_dir / group['name'] / f"Channel-{short_name}")
        
        actual_track_count = 0
        found_folder = None
        
        for channel_folder in possible_folders:
            if channel_folder.exists():
                found_folder = channel_folder
                video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mp3', '.m4a']  # Include audio too
                actual_track_count = len([f for f in channel_folder.iterdir() 
                                        if f.is_file() and f.suffix.lower() in video_extensions])
                break
        
        # Update database with actual count
        db.update_channel_sync(conn, channel_id, actual_track_count)
        conn.close()
        
        folder_info = f" in {found_folder}" if found_folder else " (folder not found)"
        log_message(f"[Channels] Refreshed stats for {channel['name']}: {actual_track_count} tracks{folder_info}")
        
        return jsonify({
            "status": "success", 
            "track_count": actual_track_count,
            "message": f"Statistics updated: {actual_track_count} tracks found"
        })
        
    except Exception as e:
        log_message(f"[Channels] Error refreshing channel stats: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/delete_track", methods=["POST"])
def api_delete_track():
    """Delete a track from playlist by moving it to trash."""
    try:
        data = request.get_json() or {}
        video_id = data.get('video_id')
        
        log_message(f"[Delete] DEBUG: Received delete request")
        log_message(f"[Delete] DEBUG: Request data: {data}")
        log_message(f"[Delete] DEBUG: Video ID: {video_id}")
        
        # Validate required fields
        if not video_id:
            log_message(f"[Delete] ERROR: No video_id provided in request")
            return jsonify({"status": "error", "error": "Video ID is required"}), 400
        
        conn = get_connection()
        
        # Get track information from database
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, relpath, video_id, channel_group
            FROM tracks 
            WHERE video_id = ?
        """, (video_id,))
        
        track = cursor.fetchone()
        if not track:
            log_message(f"[Delete] ERROR: Track not found in database for video_id: {video_id}")
            
            # Let's try to find this track by searching for similar patterns
            log_message(f"[Delete] DEBUG: Searching for tracks with similar video_id patterns...")
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE video_id LIKE ?
                ORDER BY id DESC
                LIMIT 5
            """, (f"%{video_id}%",))
            
            similar_tracks = cursor.fetchall()
            if similar_tracks:
                log_message(f"[Delete] DEBUG: Found {len(similar_tracks)} tracks with similar video_id:")
                for i, sim_track in enumerate(similar_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{sim_track[0]} video_id:'{sim_track[3]}' name:'{sim_track[1]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found with similar video_id patterns")
            
            # Try to find by filename pattern
            filename_pattern = f"%{video_id}%"
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE name LIKE ? OR relpath LIKE ?
                ORDER BY id DESC
                LIMIT 5
            """, (filename_pattern, filename_pattern))
            
            filename_matches = cursor.fetchall()
            if filename_matches:
                log_message(f"[Delete] DEBUG: Found {len(filename_matches)} tracks with filename pattern:")
                for i, match_track in enumerate(filename_matches):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{match_track[0]} video_id:'{match_track[3]}' name:'{match_track[1]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found with filename pattern")
            
            # Check if there are ANY tracks from the same channel/folder
            log_message(f"[Delete] DEBUG: Checking for tracks in Channel-Halsey folder...")
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                WHERE relpath LIKE '%Channel-Halsey%'
                ORDER BY id DESC
                LIMIT 5
            """)
            
            halsey_tracks = cursor.fetchall()
            if halsey_tracks:
                log_message(f"[Delete] DEBUG: Found {len(halsey_tracks)} tracks in Channel-Halsey:")
                for i, halsey_track in enumerate(halsey_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{halsey_track[0]} video_id:'{halsey_track[3]}' path:'{halsey_track[2]}'")
            else:
                log_message(f"[Delete] DEBUG: No tracks found in Channel-Halsey folder in database!")
            
            # Show some recent tracks for context
            cursor.execute("""
                SELECT id, name, relpath, video_id, channel_group
                FROM tracks 
                ORDER BY id DESC
                LIMIT 3
            """)
            
            recent_tracks = cursor.fetchall()
            if recent_tracks:
                log_message(f"[Delete] DEBUG: Last 3 tracks in database for reference:")
                for i, rec_track in enumerate(recent_tracks):
                    log_message(f"[Delete] DEBUG:   {i+1}. ID:{rec_track[0]} video_id:'{rec_track[3]}' name:'{rec_track[1]}'")
            
            # Check total track count
            cursor.execute("SELECT COUNT(*) FROM tracks")
            total_count = cursor.fetchone()[0]
            log_message(f"[Delete] DEBUG: Total tracks in database: {total_count}")
            
            # Try to scan this specific file and see what video_id it would extract
            log_message(f"[Delete] DEBUG: Attempting to simulate file scan for debugging...")
            
            # Get the file path that was being played
            media_path = data.get('file_path', '')  # We need to add this to the request
            if not media_path:
                log_message(f"[Delete] DEBUG: No file_path provided, cannot simulate scan")
            else:
                import re
                from pathlib import Path
                
                # Decode URL encoding if present
                from urllib.parse import unquote
                decoded_path = unquote(media_path)
                log_message(f"[Delete] DEBUG: Media path from request: {decoded_path}")
                
                # Extract filename
                file_path = Path(decoded_path)
                file_stem = file_path.stem
                log_message(f"[Delete] DEBUG: File stem for regex: '{file_stem}'")
                
                # Apply same regex as scan_tracks
                video_id_match = re.search(r"\[([A-Za-z0-9_-]{11})\]$", file_stem)
                extracted_video_id = video_id_match.group(1) if video_id_match else None
                
                log_message(f"[Delete] DEBUG: Regex match result: {video_id_match}")
                log_message(f"[Delete] DEBUG: Extracted video_id from filename: '{extracted_video_id}'")
                log_message(f"[Delete] DEBUG: Requested video_id: '{video_id}'")
                log_message(f"[Delete] DEBUG: video_id match: {extracted_video_id == video_id}")
            
            conn.close()
            return jsonify({"status": "error", "error": "Track not found in database. Please rescan files first."}), 404
        
        track_id = track[0]
        track_name = track[1]
        track_relpath = track[2]
        channel_group = track[4] if track[4] else 'Unknown'
        
        log_message(f"[Delete] DEBUG: Found track in database:")
        log_message(f"[Delete] DEBUG: - Track ID: {track_id}")
        log_message(f"[Delete] DEBUG: - Track Name: {track_name}")
        log_message(f"[Delete] DEBUG: - Relative Path: {track_relpath}")
        log_message(f"[Delete] DEBUG: - Video ID: {video_id}")
        log_message(f"[Delete] DEBUG: - Channel Group: {channel_group}")
        
        # Construct full file path
        root_dir = get_root_dir()
        if not root_dir:
            log_message(f"[Delete] ERROR: ROOT_DIR not initialized")
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
            
        log_message(f"[Delete] DEBUG: ROOT_DIR: {root_dir}")
        
        full_file_path = root_dir / track_relpath
        log_message(f"[Delete] DEBUG: Full file path to delete: {full_file_path}")
        log_message(f"[Delete] DEBUG: Full file path absolute: {full_file_path.resolve()}")
        log_message(f"[Delete] DEBUG: File exists check: {full_file_path.exists()}")
        
        if not full_file_path.exists():
            log_message(f"[Delete] ERROR: File not found on disk: {full_file_path}")
            log_message(f"[Delete] ERROR: Attempted to access: {full_file_path.resolve()}")
            return jsonify({"status": "error", "error": "File not found on disk"}), 404
        
        # Extract channel name from YouTube metadata for trash organization
        # Based on user requirement: D:\music\Youtube\Playlists\Trash\@channelname\videos\
        channel_folder = "Unknown"
        log_message(f"[Delete] Analyzing track path: {track_relpath}")
        
        # Try to get channel info from youtube_video_metadata first
        try:
            cursor.execute("""
                SELECT channel, channel_url, uploader_url
                FROM youtube_video_metadata 
                WHERE youtube_id = ?
            """, (video_id,))
            
            metadata = cursor.fetchone()
            if metadata:
                channel_name = metadata[0]  # channel
                channel_url = metadata[1]   # channel_url
                uploader_url = metadata[2]  # uploader_url
                
                # Extract @channelname from URLs
                extracted_name = None
                
                # Try channel_url first (e.g., https://www.youtube.com/@halsey)
                if channel_url and '@' in channel_url:
                    url_parts = channel_url.split('@')
                    if len(url_parts) > 1:
                        extracted_name = url_parts[1].split('/')[0]
                        log_message(f"[Delete] Extracted @{extracted_name} from channel_url: {channel_url}")
                
                # Try uploader_url as backup (e.g., https://www.youtube.com/@halsey)
                elif uploader_url and '@' in uploader_url:
                    url_parts = uploader_url.split('@')
                    if len(url_parts) > 1:
                        extracted_name = url_parts[1].split('/')[0]
                        log_message(f"[Delete] Extracted @{extracted_name} from uploader_url: {uploader_url}")
                
                # Use extracted name if found, otherwise use channel name
                if extracted_name:
                    channel_folder = extracted_name.replace(' ', '_')
                elif channel_name:
                    channel_folder = channel_name.replace(' ', '_')
                
                log_message(f"[Delete] Using YouTube metadata channel: {channel_folder}")
            else:
                log_message(f"[Delete] No YouTube metadata found for video_id: {video_id}")
        except Exception as e:
            log_message(f"[Delete] Error getting YouTube metadata: {e}")
        
        # Fallback to path-based extraction if metadata didn't work
        if channel_folder == "Unknown":
            if "Channel-" in track_relpath:
                # Extract channel name from path like "New Music/Channel-Artist/video.mp4"
                channel_match = re.search(r'Channel-([^/\\]+)', track_relpath)
                if channel_match:
                    channel_folder = channel_match.group(1).replace(' ', '_')
                    log_message(f"[Delete] Extracted from Channel- pattern: {channel_folder}")
                else:
                    log_message(f"[Delete] Found Channel- in path but failed to extract name")
            else:
                # For regular playlists, use the playlist name as channel
                path_parts = Path(track_relpath).parts
                if len(path_parts) > 0:
                    channel_folder = path_parts[0].replace(' ', '_')
                    log_message(f"[Delete] Using playlist name as channel: {channel_folder}")
        
        log_message(f"[Delete] Final channel folder for trash: {channel_folder}")
        
        # Create trash directory structure: Trash/channelname/videos/
        # ROOT_DIR points to D:\music\Youtube\Playlists, so we need to go up one level for Trash
        trash_dir = root_dir.parent / "Trash" / channel_folder / "videos"
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize filename for Windows filesystem compatibility
        def sanitize_filename(filename):
            """Remove or replace invalid characters for Windows filesystem"""
            # Invalid characters for Windows: < > : " | ? * and control chars
            invalid_chars = '<>:"|?*'
            sanitized = filename
            for char in invalid_chars:
                sanitized = sanitized.replace(char, '_')
            # Also replace control characters
            sanitized = ''.join(c if ord(c) >= 32 else '_' for c in sanitized)
            return sanitized.strip()
        
        # Generate unique filename in trash if file already exists
        sanitized_name = sanitize_filename(full_file_path.name)
        target_file = trash_dir / sanitized_name
        
        if target_file.exists():
            # Add timestamp to avoid conflicts
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name_parts = sanitized_name.rsplit('.', 1)
            if len(name_parts) == 2:
                new_name = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            else:
                new_name = f"{sanitized_name}_{timestamp}"
            target_file = trash_dir / new_name
            
        log_message(f"[Delete] Sanitized filename: {full_file_path.name} → {target_file.name}")
        
        # Move file to trash with retry mechanism for Windows file locks
        import time
        
        def move_file_with_retry(source_path, target_path, max_retries=3, delay=0.5):
            """
            Move file with retry mechanism to handle Windows file locks.
            
            Args:
                source_path: Source file path
                target_path: Target file path  
                max_retries: Maximum number of retry attempts
                delay: Delay between retries in seconds
                
            Returns:
                True if successful, False otherwise
            """
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        # Wait before retry
                        log_message(f"[Delete] Retry attempt {attempt}/{max_retries} after {delay}s delay...")
                        time.sleep(delay)
                        
                        # Check if file is still being used
                        try:
                            # Try to open file in exclusive mode to check if it's locked
                            with open(source_path, 'r+b') as test_file:
                                pass  # File is not locked
                            log_message(f"[Delete] File appears to be unlocked, proceeding with move...")
                        except (OSError, IOError) as lock_error:
                            if attempt == max_retries:
                                log_message(f"[Delete] File still locked after {max_retries} retries: {lock_error}")
                                return False
                            else:
                                log_message(f"[Delete] File still locked, will retry: {lock_error}")
                                continue
                    
                    log_message(f"[Delete] Attempting to move file (attempt {attempt + 1}/{max_retries + 1})")
                    log_message(f"[Delete] Moving file: {source_path} → {target_path}")
                    
                    shutil.move(source_path, target_path)
                    log_message(f"[Delete] SUCCESS: File moved successfully on attempt {attempt + 1}")
                    return True
                    
                except OSError as e:
                    # Check if this is a Windows file lock error
                    if "being used by another process" in str(e) or "WinError 32" in str(e):
                        log_message(f"[Delete] Attempt {attempt + 1} failed with file lock error: {e}")
                        if attempt == max_retries:
                            log_message(f"[Delete] Final attempt failed - file is locked by another process")
                            return False
                        # Continue to next retry
                        continue
                    else:
                        # Different error, don't retry
                        log_message(f"[Delete] Move failed with non-lock error: {e}")
                        return False
                except Exception as e:
                    log_message(f"[Delete] Move failed with unexpected error: {e}")
                    return False
            
            return False
        
        try:
            # Convert to absolute paths to avoid relative path issues
            source_path = str(full_file_path.resolve())
            target_path = str(target_file.resolve())
            
            log_message(f"[Delete] DEBUG: Preparing to move file:")
            log_message(f"[Delete] DEBUG: - Source path: {source_path}")
            log_message(f"[Delete] DEBUG: - Target path: {target_path}")
            log_message(f"[Delete] DEBUG: - Target directory exists: {target_file.parent.exists()}")
            log_message(f"[Delete] DEBUG: - Source file exists: {full_file_path.exists()}")
            log_message(f"[Delete] DEBUG: - Source file readable: {full_file_path.is_file()}")
            
            # Add small initial delay to give client time to release file
            log_message(f"[Delete] Waiting briefly for client to release file lock...")
            time.sleep(0.3)
            
            # Attempt file move with retry mechanism
            move_success = move_file_with_retry(source_path, target_path)
            
            if not move_success:
                error_msg = "Failed to move file to trash - file may still be in use by media player. Please try again in a moment."
                log_message(f"[Delete] ERROR: {error_msg}")
                return jsonify({"status": "error", "error": error_msg}), 500
            
            # Calculate trash_path relative to ROOT_DIR parent (D:\music\Youtube)
            trash_path = str(target_file.relative_to(root_dir.parent))
            log_message(f"[Delete] SUCCESS: Moved to trash: {track_name} → {trash_path}")
            log_message(f"[Delete] DEBUG: Target file created successfully: {target_file.exists()}")
            
        except Exception as e:
            log_message(f"[Delete] ERROR: Unexpected error during file move: {e}")
            log_message(f"[Delete] ERROR: Exception type: {type(e).__name__}")
            log_message(f"[Delete] ERROR: Source path: {source_path}")
            log_message(f"[Delete] ERROR: Target path: {target_path}")
            return jsonify({"status": "error", "error": f"Failed to move file to trash: {e}"}), 500
        
        # Record deletion in database
        db.record_track_deletion(
            conn, 
            video_id, 
            track_name, 
            track_relpath, 
            deletion_reason='manual_delete',
            channel_group=channel_folder,
            trash_path=trash_path,
            additional_data=f"deleted_from_playlist_ui"
        )
        
        # Record deletion event in play_history with full path information
        full_source_path = str(full_file_path)
        full_target_path = str(target_file)
        record_event(conn, video_id, 'removed', additional_data=f'manual_delete_move_from:{full_source_path}_to:{full_target_path}')
        
        conn.close()
        
        log_message(f"[Delete] Successfully deleted track {video_id} ({track_name}) to trash")
        return jsonify({
            "status": "ok",
            "message": f"Track moved to trash: {channel_folder}/videos/{target_file.name}",
            "video_id": video_id,
            "track_name": track_name,
            "trash_path": trash_path
        })
        
    except Exception as e:
        log_message(f"[Delete] Error deleting track: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/rescan_files", methods=["POST"])
def api_rescan_files():
    """Rescan all files and add missing tracks to database."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "ROOT_DIR not initialized"}), 500
        
        log_message(f"[Rescan] Starting file rescan from: {root_dir}")
        
        # Import scan functionality
        from pathlib import Path
        import subprocess
        
        MEDIA_EXTS = {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
        VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
        
        def get_video_id(stem: str):
            m = VIDEO_ID_RE.search(stem)
            return m.group(1) if m else None
        
        def ffprobe_duration(path: Path):
            try:
                res = subprocess.run([
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration:stream=bit_rate,width,height",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path)
                ], capture_output=True, text=True, check=True, timeout=10)
                lines = res.stdout.strip().split("\n")
                duration = float(lines[0]) if lines else None
                bitrate = None
                resolution = None
                for line in lines[1:]:
                    if not bitrate and line.isdigit():
                        bitrate = int(line)
                    elif "x" in line and line.replace("x", "").replace("N/A", "").isdigit():
                        resolution = line
                return duration, bitrate, resolution
            except Exception:
                return None, None, None
        
        # Scan all directories
        conn = get_connection()
        total_added = 0
        total_playlists = 0
        
        for playlist_dir in root_dir.iterdir():
            if not playlist_dir.is_dir():
                continue
            
            # Check if has media files
            has_media = any(p.suffix.lower() in MEDIA_EXTS for p in playlist_dir.rglob("*.*"))
            if not has_media:
                continue
            
            playlist_rel = str(playlist_dir.relative_to(root_dir))
            log_message(f"[Rescan] Processing playlist: {playlist_dir.name}")
            
            # Upsert playlist
            playlist_id = db.upsert_playlist(conn, playlist_dir.name, playlist_rel)
            total_playlists += 1
            
            count = 0
            processed_track_ids = set()
            
            for file in playlist_dir.rglob("*.*"):
                if file.suffix.lower() not in MEDIA_EXTS or not file.is_file():
                    continue
                
                video_id = get_video_id(file.stem)
                if not video_id:
                    continue  # Skip files without recognized ID
                
                # Check if track already exists
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM tracks WHERE video_id = ?", (video_id,))
                existing = cursor.fetchone()
                
                if existing:
                    track_id = existing[0]
                    log_message(f"[Rescan] Track exists: {video_id}")
                else:
                    # Add new track
                    duration, bitrate, resolution = ffprobe_duration(file)
                    size_bytes = file.stat().st_size
                    track_id = db.upsert_track(
                        conn,
                        video_id=video_id,
                        name=file.stem,
                        relpath=str(file.relative_to(root_dir)),
                        duration=duration,
                        size_bytes=size_bytes,
                        bitrate=bitrate,
                        resolution=resolution,
                        filetype=file.suffix.lstrip(".").lower(),
                    )
                    total_added += 1
                    log_message(f"[Rescan] Added track: {video_id} - {file.stem}")
                
                # Link to playlist
                db.link_track_playlist(conn, track_id, playlist_id)
                processed_track_ids.add(track_id)
                count += 1
            
            # Remove stale links
            cursor = conn.cursor()
            cursor.execute("SELECT track_id FROM track_playlists WHERE playlist_id=?", (playlist_id,))
            existing_links = {row[0] for row in cursor.fetchall()}
            to_remove = existing_links - processed_track_ids
            if to_remove:
                cursor.executemany(
                    "DELETE FROM track_playlists WHERE playlist_id=? AND track_id=?",
                    [(playlist_id, tid) for tid in to_remove],
                )
                conn.commit()
            
            # Update playlist stats
            db.update_playlist_stats(conn, playlist_id, count)
            log_message(f"[Rescan] Playlist {playlist_dir.name}: {count} tracks")
        
        conn.close()
        
        log_message(f"[Rescan] Completed: {total_added} new tracks added to {total_playlists} playlists")
        return jsonify({
            "status": "ok", 
            "message": f"Rescan completed: {total_added} new tracks added to {total_playlists} playlists",
            "tracks_added": total_added,
            "playlists_processed": total_playlists
        })
        
    except Exception as e:
        log_message(f"[Rescan] Error during file rescan: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_bp.route("/remove_channel/<int:channel_id>", methods=["POST"])
def api_remove_channel(channel_id: int):
    """Remove channel from its group."""
    try:
        data = request.get_json() or {}
        keep_files = data.get('keep_files', True)  # Default: keep files on disk
        
        conn = get_connection()
        
        # Get channel info before deletion 
        channel_raw = db.get_channel_by_id(conn, channel_id)
        if not channel_raw:
            conn.close()
            return jsonify({"status": "error", "error": "Channel not found"}), 404
        
        channel = dict(channel_raw)
        
        # Get group info for folder path
        group = db.get_channel_group_by_id(conn, channel['channel_group_id'])
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Remove channel from database
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        conn.commit()
        
        removed_count = cursor.rowcount
        conn.close()
        
        if removed_count > 0:
            log_message(f"[Channels] Removed channel '{channel['name']}' from group '{group['name']}'")
            
            # Optional: Remove files from disk
            if not keep_files:
                # Try multiple possible folder names (same logic as refresh_stats)
                root_dir = get_root_dir()
                if not root_dir:
                    return jsonify({"status": "error", "error": "Server configuration error"}), 500
                    
                possible_folders = []
                possible_folders.append(root_dir / group['name'] / f"Channel-{channel['name']}")
                
                if '@' in channel['url']:
                    url_channel_name = channel['url'].split('@')[1].split('/')[0]
                    possible_folders.append(root_dir / group['name'] / f"Channel-{url_channel_name}")
                
                short_name = channel['name'].replace('enjoy', '').replace('music', '').replace('official', '').strip()
                if short_name != channel['name']:
                    possible_folders.append(root_dir / group['name'] / f"Channel-{short_name}")
                
                deleted_folder = None
                for channel_folder in possible_folders:
                    if channel_folder.exists():
                        try:
                            shutil.rmtree(channel_folder)
                            deleted_folder = channel_folder
                            log_message(f"[Channels] Deleted folder: {channel_folder}")
                            break
                        except Exception as e:
                            log_message(f"[Channels] Error deleting folder {channel_folder}: {e}")
                
                folder_info = f" and deleted folder {deleted_folder}" if deleted_folder else " (folder not found)"
            else:
                folder_info = " (files kept on disk)"
            
            return jsonify({
                "status": "success",
                "message": f"Channel '{channel['name']}' removed from group '{group['name']}'{folder_info}",
                "channel_name": channel['name'],
                "group_name": group['name'],
                "files_deleted": not keep_files
            })
        else:
            return jsonify({"status": "error", "error": "Channel not found or already removed"}), 404
            
    except Exception as e:
        log_message(f"[Channels] Error removing channel: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500