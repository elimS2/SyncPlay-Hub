"""Channel Management API endpoints."""

import re
import threading
import shutil
import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event
import database as db
from utils.youtube_channel_urls import extract_video_id_from_url, is_video_url

# Create blueprint
channels_management_bp = Blueprint('channels_management', __name__)

_CHANNEL_FORMAT_SELECTOR = (
    'bestvideo[ext=mp4][vcodec*=avc1][height>=2160]+bestaudio[ext=m4a]/'
    'bestvideo[ext=mp4][vcodec*=avc1][height>=1440]+bestaudio[ext=m4a]/'
    'bestvideo[ext=mp4][vcodec*=avc1][height>=1080]+bestaudio[ext=m4a]/'
    '137+140/bestvideo[height>=1080]+bestaudio'
)


def _channel_handle_candidates(metadata: dict) -> list[str]:
    """Build ordered list of possible channel folder name stems from video metadata."""
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value:
            return
        cleaned = value.strip().lstrip('@')
        if cleaned and not cleaned.startswith('UC') and cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    add(metadata.get('uploader_id'))
    uploader_url = metadata.get('uploader_url') or ''
    if '@' in uploader_url:
        add(uploader_url.split('@')[1].split('/')[0].split('?')[0])
    channel_url = metadata.get('channel_url') or ''
    if '@' in channel_url:
        add(channel_url.split('@')[1].split('/')[0].split('?')[0])
    return candidates


def _resolve_channel_folder_name(
    conn,
    group_id: int,
    group_name: str,
    root_dir: Path,
    metadata: dict,
) -> str:
    """Pick Channel-{name} folder stem for a one-off video download."""
    uploader_id = (metadata.get('uploader_id') or '').strip()
    channel_id = (metadata.get('channel_id') or '').strip()
    uploader_url = (metadata.get('uploader_url') or '').split('?')[0]
    channel_url = (metadata.get('channel_url') or '').split('?')[0]

    for channel in db.get_channels_by_group(conn, group_id):
        ch = dict(channel)
        ch_url = ch.get('url') or ''
        ch_name = ch.get('name') or ''
        if uploader_id and f'@{uploader_id.lstrip("@")}' in ch_url:
            return ch_name
        if channel_id and channel_id in ch_url:
            return ch_name
        if uploader_url and uploader_url in ch_url:
            return ch_name
        if channel_url and channel_url in ch_url:
            return ch_name

    group_dir = root_dir / group_name
    for candidate in _channel_handle_candidates(metadata):
        folder = group_dir / f"Channel-{candidate}"
        if folder.exists():
            return candidate

    candidates = _channel_handle_candidates(metadata)
    if candidates:
        return candidates[0]

    channel_title = (metadata.get('channel') or metadata.get('uploader') or 'Unknown').strip()
    sanitized = re.sub(r'[^\w-]', '', channel_title.replace(' ', ''))
    return sanitized or 'Unknown'

@channels_management_bp.route("/add_channel", methods=["POST"])
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
            r'youtube\.com/@([^/\s]+)(?:/(?:videos|releases))?',  # @ChannelName, /videos or /releases
            r'youtube\.com/c/([^/\s]+)(?:/(?:videos|releases))?',  # /c/ChannelName
            r'youtube\.com/channel/([^/\s]+)(?:/(?:videos|releases))?',  # /channel/ChannelID
            r'youtube\.com/user/([^/\s]+)(?:/(?:videos|releases))?'  # /user/Username
        ]
        
        valid_url = False
        for pattern in channel_patterns:
            if re.search(pattern, channel_url):
                valid_url = True
                break
        
        if not valid_url:
            return jsonify({
                "status": "error", 
                "error": "Invalid YouTube channel URL. Supported formats: @ChannelName/videos, @ChannelName/releases, /c/ChannelName, /channel/ChannelID, /user/Username"
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
                            log_message(f"[Channel Add] Creating download job for {video_id} with video_id={video_id}, skip_full_scan=True")
                            job_id = job_service.create_and_add_job(
                                JobType.SINGLE_VIDEO_DOWNLOAD,
                                priority=JobPriority.NORMAL,
                                playlist_url=video_url,
                                target_folder=target_folder,
                                # Prefer ≥1080p with MP4/AVC1 when available; allow higher (4K/2K) first
                                format_selector='bestvideo[ext=mp4][vcodec*=avc1][height>=2160]+bestaudio[ext=m4a]/bestvideo[ext=mp4][vcodec*=avc1][height>=1440]+bestaudio[ext=m4a]/bestvideo[ext=mp4][vcodec*=avc1][height>=1080]+bestaudio[ext=m4a]/137+140/bestvideo[height>=1080]+bestaudio',
                                extract_audio=False,  # Download video files for channels
                                download_archive=True,
                                exclude_shorts=True,  # Exclude YouTube Shorts
                                video_id=video_id,  # Pass video_id for automatic media probing
                                skip_full_scan=True  # Enable optimized single-track update with media probing
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


@channels_management_bp.route("/download_track", methods=["POST"])
def api_download_track():
    """Download a single YouTube video into the channel folder (no subscription)."""
    try:
        data = request.get_json() or {}
        group_id = data.get('group_id')
        video_url = (data.get('url') or '').strip()

        if not group_id:
            return jsonify({"status": "error", "error": "Group ID is required"}), 400
        if not video_url:
            return jsonify({"status": "error", "error": "Video URL is required"}), 400
        if not is_video_url(video_url):
            return jsonify({
                "status": "error",
                "error": "Invalid YouTube video URL. Supported: watch?v=, youtu.be/, shorts/",
            }), 400

        video_id = extract_video_id_from_url(video_url)
        if not video_id:
            return jsonify({"status": "error", "error": "Could not extract video ID from URL"}), 400

        conn = get_connection()
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404

        if db.is_track_already_downloaded(conn, video_id):
            conn.close()
            return jsonify({
                "status": "error",
                "error": f"Video {video_id} is already in the library",
            }), 400

        group_name = group['name']
        conn.close()

        from services.job_queue_service import get_job_queue_service
        from services.job_types import JobType, JobPriority

        job_service = get_job_queue_service()

        def metadata_completion_callback(job_id: int, success: bool, error_message: str = None):
            if not success:
                log_message(f"[Download Track] Metadata extraction failed for {video_id}: {error_message}")
                return

            try:
                conn = get_connection()
                meta_row = db.get_youtube_metadata_by_id(conn, video_id)
                if not meta_row:
                    conn.close()
                    log_message(f"[Download Track] No metadata found for {video_id} after extraction")
                    return

                metadata = dict(meta_row)
                root_dir = get_root_dir()
                if not root_dir:
                    conn.close()
                    log_message("[Download Track] ROOT_DIR not initialized")
                    return

                channel_name = _resolve_channel_folder_name(conn, group_id, group_name, root_dir, metadata)
                target_folder = f"{group_name}/Channel-{channel_name}"
                video_title = metadata.get('title') or f"Video {video_id}"
                conn.close()

                download_job_id = job_service.create_and_add_job(
                    JobType.SINGLE_VIDEO_DOWNLOAD,
                    priority=JobPriority.HIGH,
                    playlist_url=f"https://www.youtube.com/watch?v={video_id}",
                    target_folder=target_folder,
                    format_selector=_CHANNEL_FORMAT_SELECTOR,
                    extract_audio=False,
                    download_archive=True,
                    exclude_shorts=False,
                    video_id=video_id,
                    skip_full_scan=True,
                )
                log_message(
                    f"[Download Track] Queued download job #{download_job_id} for "
                    f"'{video_title[:50]}' -> {target_folder}"
                )
            except Exception as exc:
                log_message(f"[Download Track] Error creating download job for {video_id}: {exc}")

        metadata_job_id = job_service.create_and_add_job(
            JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
            callback=metadata_completion_callback,
            priority=JobPriority.HIGH,
            video_id=video_id,
            force_update=True,
        )

        log_message(
            f"[Download Track] One-off download started for {video_url} "
            f"in group '{group_name}' (metadata job #{metadata_job_id})"
        )

        return jsonify({
            "status": "started",
            "video_id": video_id,
            "metadata_job_id": metadata_job_id,
            "message": (
                f"Track download started in group '{group_name}'. "
                "No channel subscription will be created."
            ),
            "process": "single_track",
            "steps": [
                "1. Extract video metadata (in progress)",
                "2. Resolve channel folder and download video (pending)",
                "3. Update library database (pending)",
            ],
        })

    except ImportError:
        return jsonify({"status": "error", "error": "Job queue system is not available"}), 503
    except Exception as e:
        log_message(f"[Channels] Error starting track download: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@channels_management_bp.route("/remove_channel/<int:channel_id>", methods=["POST"])
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

@channels_management_bp.route("/refresh_channel_stats/<int:channel_id>", methods=["POST"])
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
        
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500

        actual_track_count = db.count_channel_downloaded_tracks(
            conn,
            channel['url'],
            group_name=group['name'],
            channel_name=channel['name'],
            root_dir=root_dir,
        )

        # Update database with actual count
        db.update_channel_sync(conn, channel_id, actual_track_count)
        conn.close()
        
        folder_info = ""
        log_message(f"[Channels] Refreshed stats for {channel['name']}: {actual_track_count} tracks{folder_info}")
        
        return jsonify({
            "status": "success", 
            "track_count": actual_track_count,
            "message": f"Statistics updated: {actual_track_count} tracks found"
        })
        
    except Exception as e:
        log_message(f"[Channels] Error refreshing channel stats: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 