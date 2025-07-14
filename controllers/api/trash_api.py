"""Trash API endpoints."""

import json
import shutil
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event, _format_file_size
import database as db

# Create blueprint
trash_bp = Blueprint('trash', __name__)

@trash_bp.route("/deleted_tracks")
def api_get_deleted_tracks():
    """Get deleted tracks for restoration page."""
    try:
        conn = get_connection()
        deleted_tracks_raw = db.get_deleted_tracks(conn)
        
        # Convert SQLite Row objects to dictionaries for JSON serialization
        deleted_tracks = []
        for row in deleted_tracks_raw:
            track_dict = dict(row)
            deleted_tracks.append(track_dict)
        
        # DEBUG: Add restoration analysis for each track
        log_message(f"[Restore] DEBUG: Analyzing {len(deleted_tracks)} deleted tracks for restoration")
        
        for i, track in enumerate(deleted_tracks):
            if i < 5:  # Only log first 5 tracks to avoid spam
                log_message(f"[Restore] DEBUG Track {i+1}:")
                log_message(f"  - video_id: {track.get('video_id')}")
                log_message(f"  - original_name: {track.get('original_name')}")
                log_message(f"  - original_relpath: {track.get('original_relpath')}")
                log_message(f"  - channel_group: {track.get('channel_group')}")
                log_message(f"  - trash_path: {track.get('trash_path')}")
                log_message(f"  - can_restore: {track.get('can_restore')}")
                log_message(f"  - restoration_method: {track.get('restoration_method')}")
                
                # Analyze what folder this track should be restored to
                original_path = track.get('original_relpath', '')
                if original_path:
                    # Extract playlist/folder info from original path (cross-platform)
                    path_obj = Path(original_path)
                    path_parts = path_obj.parts
                    
                    if len(path_parts) >= 2:
                        playlist_folder = path_parts[0]  # First part is playlist folder
                        channel_folder = path_parts[1]   # Second part is channel folder
                        log_message(f"  - target_folder: {playlist_folder}")
                        log_message(f"  - channel_folder: {channel_folder}")
                        track['target_folder'] = playlist_folder
                        track['channel_folder'] = channel_folder
                    elif len(path_parts) == 1:
                        # Single level path
                        playlist_folder = path_parts[0]
                        log_message(f"  - target_folder: {playlist_folder}")
                        track['target_folder'] = playlist_folder
                        track['channel_folder'] = None
                    else:
                        log_message(f"  - target_folder: Could not determine from path")
                        track['target_folder'] = 'Unknown'
                        track['channel_folder'] = None
                else:
                    log_message(f"  - target_folder: No original_relpath available")
                    track['target_folder'] = 'Unknown'
                    track['channel_folder'] = None
        
        # Get unique channel groups for the filter
        channel_groups = []
        unique_groups = set()
        for track in deleted_tracks:
            group_name = track.get('channel_group')
            if group_name and group_name not in unique_groups:
                unique_groups.add(group_name)
                channel_groups.append({'name': group_name})
        
        # Sort channel groups alphabetically
        channel_groups.sort(key=lambda x: x['name'])
        
        conn.close()
        
        log_message(f"[Restore] Retrieved {len(deleted_tracks)} deleted tracks and {len(channel_groups)} channel groups")
        return jsonify({
            "status": "ok", 
            "tracks": deleted_tracks,
            "channel_groups": channel_groups
        })
        
    except Exception as e:
        log_message(f"[Restore] Error retrieving deleted tracks: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/restore_track", methods=["POST"])
def api_restore_track():
    """Restore a deleted track."""
    try:
        data = request.get_json() or {}
        track_id = data.get('track_id')
        restore_method = data.get('method', 'file')  # 'file' or 'redownload'
        
        log_message(f"[Restore] DEBUG: Restore request received")
        log_message(f"[Restore] DEBUG: track_id={track_id}, method={restore_method}")
        
        # Validate required fields
        if not track_id:
            return jsonify({"status": "error", "error": "Track ID is required"}), 400
        
        if restore_method not in ['file', 'redownload', 'file_restore']:
            return jsonify({"status": "error", "error": "Invalid restore method. Must be 'file', 'file_restore' or 'redownload'"}), 400
        
        conn = get_connection()
        
        # First, get detailed information about the track to be restored
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM deleted_tracks 
            WHERE id = ? AND restored_at IS NULL
        """, (track_id,))
        
        track_info = cursor.fetchone()
        if not track_info:
            conn.close()
            return jsonify({"status": "error", "error": "Track not found or already restored"}), 404
        
        # Convert to dict for easier access
        track_dict = dict(track_info)
        
        log_message(f"[Restore] DEBUG: Found track to restore:")
        log_message(f"  - video_id: {track_dict.get('video_id')}")
        log_message(f"  - original_name: {track_dict.get('original_name')}")
        log_message(f"  - original_relpath: {track_dict.get('original_relpath')}")
        log_message(f"  - channel_group: {track_dict.get('channel_group')}")
        log_message(f"  - trash_path: {track_dict.get('trash_path')}")
        log_message(f"  - can_restore: {track_dict.get('can_restore')}")
        
        # Determine target folder for restoration
        original_path = track_dict.get('original_relpath', '')
        if original_path:
            path_obj = Path(original_path)
            path_parts = path_obj.parts
            
            if len(path_parts) >= 2:
                target_folder = path_parts[0]  # First part is playlist folder
                channel_folder = path_parts[1]  # Second part is channel folder
                log_message(f"  - target_folder: {target_folder}")
                log_message(f"  - channel_folder: {channel_folder}")
            elif len(path_parts) == 1:
                target_folder = path_parts[0]
                channel_folder = None
                log_message(f"  - target_folder: {target_folder}")
            else:
                target_folder = 'Unknown'
                channel_folder = None
                log_message(f"  - target_folder: Could not determine from path")
        else:
            target_folder = 'Unknown'
            channel_folder = None
            log_message(f"  - target_folder: No original_relpath available")
        
        if restore_method == 'redownload':
            # Implement actual redownload through job queue
            log_message(f"[Restore] DEBUG: Redownload method selected - creating SINGLE_VIDEO_DOWNLOAD job")
            
            video_id = track_dict.get('video_id')
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            log_message(f"[Restore] DEBUG: Creating job with:")
            log_message(f"  - video_url: {video_url}")
            log_message(f"  - target_folder: {target_folder}")
            log_message(f"  - channel_group: {track_dict.get('channel_group')}")
            
            try:
                # Import job queue system
                from services.job_queue_service import get_job_queue_service
                from services.job_types import JobType, JobPriority
                
                # Get job service
                job_service = get_job_queue_service()
                
                # Create SINGLE_VIDEO_DOWNLOAD job
                job_id = job_service.create_and_add_job(
                    JobType.SINGLE_VIDEO_DOWNLOAD,
                    priority=JobPriority.HIGH,
                    playlist_url=video_url,
                    target_folder=target_folder,
                    format_selector='bestvideo+bestaudio/best',
                    extract_audio=False,  # Download video files for restoration
                    download_archive=True,
                    exclude_shorts=True,
                    force_overwrites=True,  # Overwrite if file exists
                    ignore_archive=True    # Ignore archive for restoration
                )
                
                log_message(f"[Restore] SUCCESS: Created SINGLE_VIDEO_DOWNLOAD job #{job_id} for video {video_id}")
                log_message(f"[Restore] Job will restore track to: {target_folder}")
                
                # Mark as restored in database AFTER creating the job
                result = db.restore_deleted_track(conn, track_id)
                
                if result:
                    log_message(f"[Restore] Track {track_id} marked as restored and queued for download")
                    
                    # Record event for restoration
                    log_message(f"[Restore] DEBUG: Recording 'track_restored' event for track {track_id}")
                    try:
                        # Prepare additional data as JSON string
                        additional_data = json.dumps({
                            "track_id": track_id,
                            "video_id": video_id,
                            "original_name": track_dict.get('original_name'),
                            "target_folder": target_folder,
                            "channel_folder": channel_folder,
                            "channel_group": track_dict.get('channel_group'),
                            "method": restore_method,
                            "job_id": job_id,
                            "video_url": video_url,
                            "original_relpath": track_dict.get('original_relpath'),
                            "trash_path": track_dict.get('trash_path')
                        })
                        
                        record_event(
                            conn,
                            video_id,
                            "track_restored",
                            additional_data=additional_data
                        )
                        log_message(f"[Restore] DEBUG: Event recorded successfully for track {track_id}")
                    except Exception as e:
                        log_message(f"[Restore] ERROR: Failed to record event for track {track_id}: {e}")
                        import traceback
                        log_message(f"[Restore] ERROR: Traceback: {traceback.format_exc()}")
                    
                    conn.close()
                    return jsonify({
                        "status": "ok", 
                        "message": f"Track queued for re-download",
                        "track_id": track_id,
                        "job_id": job_id,
                        "method": restore_method,
                        "target_folder": target_folder,
                        "video_url": video_url
                    })
                else:
                    conn.close()
                    return jsonify({"status": "error", "error": "Failed to mark track as restored"}), 500
                    
            except ImportError as e:
                log_message(f"[Restore] ERROR: Job Queue System not available: {e}")
                return jsonify({"status": "error", "error": "Job Queue System not available"}), 500
                
            except Exception as e:
                log_message(f"[Restore] ERROR: Failed to create download job: {e}")
                return jsonify({"status": "error", "error": f"Failed to create download job: {e}"}), 500
        
        # Handle file restoration method (restore from trash folder)
        elif restore_method in ['file', 'file_restore']:
            # TODO: Implement file restoration from trash folder
            log_message(f"[Restore] DEBUG: File restoration method selected")
            log_message(f"[Restore] DEBUG: Would restore from trash_path: {track_dict.get('trash_path')}")
            
            # For now, just mark as restored in database
            result = db.restore_deleted_track(conn, track_id)
            
            if result:
                log_message(f"[Restore] Track {track_id} marked as restored (method: {restore_method})")
                
                # Record event for file restoration
                log_message(f"[Restore] DEBUG: Recording 'track_restored' event for file restoration, track {track_id}")
                try:
                    # Prepare additional data as JSON string
                    additional_data = json.dumps({
                        "track_id": track_id,
                        "video_id": track_dict.get('video_id'),
                        "original_name": track_dict.get('original_name'),
                        "target_folder": target_folder,
                        "channel_folder": channel_folder,
                        "channel_group": track_dict.get('channel_group'),
                        "method": restore_method,
                        "original_relpath": track_dict.get('original_relpath'),
                        "trash_path": track_dict.get('trash_path'),
                        "note": "File restoration method selected but not fully implemented yet"
                    })
                    
                    record_event(
                        conn,
                        track_dict.get('video_id'),
                        "track_restored",
                        additional_data=additional_data
                    )
                    log_message(f"[Restore] DEBUG: File restoration event recorded successfully for track {track_id}")
                except Exception as e:
                    log_message(f"[Restore] ERROR: Failed to record file restoration event for track {track_id}: {e}")
                    import traceback
                    log_message(f"[Restore] ERROR: Traceback: {traceback.format_exc()}")
                
                conn.close()
                return jsonify({
                    "status": "placeholder", 
                    "message": f"Track marked as restored from file",
                    "track_id": track_id,
                    "method": restore_method,
                    "target_folder": target_folder,
                    "note": "File restoration implementation coming in Phase 4.2"
                })
            else:
                conn.close()
                return jsonify({"status": "error", "error": "Track not found or already restored"}), 404
        
        else:
            # Unknown restore method
            conn.close()
            return jsonify({"status": "error", "error": f"Unknown restore method: {restore_method}"}), 400
        
    except Exception as e:
        log_message(f"[Restore] Error restoring track: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/bulk_restore_tracks", methods=["POST"])
def api_bulk_restore_tracks():
    """Bulk restore multiple deleted tracks."""
    try:
        data = request.get_json() or {}
        track_ids = data.get('track_ids', [])
        restore_method = data.get('method', 'redownload')  # 'file_restore' or 'redownload'
        
        log_message(f"[Restore] DEBUG: Bulk restore request received")
        log_message(f"[Restore] DEBUG: track_ids={track_ids}, method={restore_method}")
        
        # Validate required fields
        if not track_ids or not isinstance(track_ids, list):
            return jsonify({"status": "error", "error": "track_ids array is required"}), 400
        
        if restore_method not in ['file_restore', 'redownload']:
            return jsonify({"status": "error", "error": "Invalid restore method. Must be 'file_restore' or 'redownload'"}), 400
        
        conn = get_connection()
        
        # Process each track
        results = []
        successful_jobs = []
        failed_tracks = []
        
        for track_id in track_ids:
            try:
                # Get track info
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM deleted_tracks 
                    WHERE id = ? AND restored_at IS NULL
                """, (track_id,))
                
                track_info = cursor.fetchone()
                if not track_info:
                    failed_tracks.append({
                        'track_id': track_id,
                        'error': 'Track not found or already restored'
                    })
                    continue
                
                track_dict = dict(track_info)
                
                # Determine target folder (cross-platform)
                original_path = track_dict.get('original_relpath', '')
                if original_path:
                    path_obj = Path(original_path)
                    path_parts = path_obj.parts
                    
                    if len(path_parts) >= 2:
                        target_folder = path_parts[0]
                        channel_folder = path_parts[1]
                    elif len(path_parts) == 1:
                        target_folder = path_parts[0]
                        channel_folder = None
                    else:
                        target_folder = 'Unknown'
                        channel_folder = None
                else:
                    target_folder = 'Unknown'
                    channel_folder = None
                
                if restore_method == 'redownload':
                    # Create SINGLE_VIDEO_DOWNLOAD job
                    try:
                        from services.job_queue_service import get_job_queue_service
                        from services.job_types import JobType, JobPriority
                        
                        job_service = get_job_queue_service()
                        video_id = track_dict.get('video_id')
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        job_id = job_service.create_and_add_job(
                            JobType.SINGLE_VIDEO_DOWNLOAD,
                            priority=JobPriority.HIGH,
                            playlist_url=video_url,
                            target_folder=target_folder,
                            format_selector='bestvideo+bestaudio/best',
                            extract_audio=False,
                            download_archive=True,
                            exclude_shorts=True,
                            force_overwrites=True,
                            ignore_archive=True
                        )
                        
                        # Mark as restored in database
                        db.restore_deleted_track(conn, track_id)
                        
                        # Record event for bulk restoration
                        log_message(f"[Restore] DEBUG: Recording bulk 'track_restored' event for track {track_id}")
                        try:
                            # Prepare additional data as JSON string
                            additional_data = json.dumps({
                                "track_id": track_id,
                                "video_id": video_id,
                                "original_name": track_dict.get('original_name'),
                                "target_folder": target_folder,
                                "channel_folder": channel_folder,
                                "channel_group": track_dict.get('channel_group'),
                                "method": restore_method,
                                "job_id": job_id,
                                "video_url": video_url,
                                "original_relpath": track_dict.get('original_relpath'),
                                "trash_path": track_dict.get('trash_path'),
                                "bulk_operation": True
                            })
                            
                            record_event(
                                conn,
                                video_id,
                                "track_restored",
                                additional_data=additional_data
                            )
                            log_message(f"[Restore] DEBUG: Bulk event recorded successfully for track {track_id}")
                        except Exception as e:
                            log_message(f"[Restore] ERROR: Failed to record bulk event for track {track_id}: {e}")
                            import traceback
                            log_message(f"[Restore] ERROR: Traceback: {traceback.format_exc()}")
                        
                        successful_jobs.append({
                            'track_id': track_id,
                            'job_id': job_id,
                            'video_id': video_id,
                            'target_folder': target_folder
                        })
                        
                        log_message(f"[Restore] Bulk: Created job #{job_id} for track {track_id} ({video_id})")
                        
                    except Exception as e:
                        failed_tracks.append({
                            'track_id': track_id,
                            'error': f'Failed to create download job: {str(e)}'
                        })
                        
                else:  # file_restore
                    # TODO: Implement file restoration
                    db.restore_deleted_track(conn, track_id)
                    
                    # Record event for bulk file restoration
                    log_message(f"[Restore] DEBUG: Recording bulk file 'track_restored' event for track {track_id}")
                    try:
                        # Prepare additional data as JSON string
                        additional_data = json.dumps({
                            "track_id": track_id,
                            "video_id": track_dict.get('video_id'),
                            "original_name": track_dict.get('original_name'),
                            "target_folder": target_folder,
                            "channel_folder": channel_folder,
                            "channel_group": track_dict.get('channel_group'),
                            "method": restore_method,
                            "original_relpath": track_dict.get('original_relpath'),
                            "trash_path": track_dict.get('trash_path'),
                            "bulk_operation": True,
                            "note": "File restoration method selected but not fully implemented yet"
                        })
                        
                        record_event(
                            conn,
                            track_dict.get('video_id'),
                            "track_restored",
                            additional_data=additional_data
                        )
                        log_message(f"[Restore] DEBUG: Bulk file event recorded successfully for track {track_id}")
                    except Exception as e:
                        log_message(f"[Restore] ERROR: Failed to record bulk file event for track {track_id}: {e}")
                        import traceback
                        log_message(f"[Restore] ERROR: Traceback: {traceback.format_exc()}")
                    
                    successful_jobs.append({
                        'track_id': track_id,
                        'job_id': None,
                        'video_id': track_dict.get('video_id'),
                        'target_folder': target_folder,
                        'note': 'File restoration not yet implemented'
                    })
                    
            except Exception as e:
                failed_tracks.append({
                    'track_id': track_id,
                    'error': str(e)
                })
        
        total_requested = len(track_ids)
        total_successful = len(successful_jobs)
        total_failed = len(failed_tracks)
        
        log_message(f"[Restore] Bulk restore completed:")
        log_message(f"  - Requested: {total_requested}")
        log_message(f"  - Successful: {total_successful}")
        log_message(f"  - Failed: {total_failed}")
        
        # Record summary event for bulk restore operation
        log_message(f"[Restore] DEBUG: Recording 'bulk_track_restore' summary event")
        try:
            # Prepare additional data as JSON string
            additional_data = json.dumps({
                "method": restore_method,
                "total_requested": total_requested,
                "total_successful": total_successful,
                "total_failed": total_failed,
                "successful_jobs": [job['job_id'] for job in successful_jobs if job.get('job_id')],
                "failed_track_ids": [failure['track_id'] for failure in failed_tracks],
                "operation_type": "bulk_restore"
            })
            
            record_event(
                conn,
                "system",  # Use "system" as video_id for bulk operations
                "bulk_track_restore",
                additional_data=additional_data
            )
            log_message(f"[Restore] DEBUG: Summary event recorded successfully")
        except Exception as e:
            log_message(f"[Restore] ERROR: Failed to record summary event: {e}")
            import traceback
            log_message(f"[Restore] ERROR: Traceback: {traceback.format_exc()}")
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "message": f"Bulk restore completed: {total_successful}/{total_requested} successful",
            "method": restore_method,
            "total_requested": total_requested,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "successful_jobs": successful_jobs,
            "failed_tracks": failed_tracks
        })
        
    except Exception as e:
        log_message(f"[Restore] Error in bulk restore: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/trash_stats")
def api_get_trash_stats():
    """Get trash folder statistics (size and file count) and disk space info."""
    try:
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        trash_dir = root_dir.parent / "Trash"
        
        # Get disk usage for the storage directory
        try:
            disk_usage = shutil.disk_usage(str(root_dir))
            disk_total = disk_usage.total
            disk_free = disk_usage.free
            disk_used = disk_total - disk_free
            
            # Format disk space values
            disk_total_formatted = _format_file_size(disk_total)
            disk_free_formatted = _format_file_size(disk_free)
            disk_used_formatted = _format_file_size(disk_used)
            
            # Calculate used percentage
            disk_used_percentage = (disk_used / disk_total) * 100 if disk_total > 0 else 0
            
            log_message(f"[Trash] Disk usage: {disk_used_formatted} / {disk_total_formatted} ({disk_used_percentage:.1f}% used)")
            
        except Exception as e:
            log_message(f"[Trash] Warning: Could not get disk usage: {e}")
            # Set default values if disk usage cannot be retrieved
            disk_total = 0
            disk_free = 0
            disk_used = 0
            disk_total_formatted = "Unknown"
            disk_free_formatted = "Unknown"
            disk_used_formatted = "Unknown"
            disk_used_percentage = 0
        
        if not trash_dir.exists():
            return jsonify({
                "status": "ok",
                "total_size": 0,
                "total_files": 0,
                "formatted_size": "0 B",
                "trash_path": str(trash_dir),
                "disk_info": {
                    "total": disk_total,
                    "free": disk_free,
                    "used": disk_used,
                    "total_formatted": disk_total_formatted,
                    "free_formatted": disk_free_formatted,
                    "used_formatted": disk_used_formatted,
                    "used_percentage": disk_used_percentage,
                    "storage_path": str(root_dir)
                }
            })
        
        total_size = 0
        total_files = 0
        
        # Recursively calculate size of all files in trash
        for file_path in trash_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    total_files += 1
                except (OSError, PermissionError) as e:
                    log_message(f"[Trash] Warning: Could not access {file_path}: {e}")
                    continue
        
        # Format size for display
        formatted_size = _format_file_size(total_size)
        
        log_message(f"[Trash] Statistics: {total_files} files, {formatted_size}")
        
        return jsonify({
            "status": "ok",
            "total_size": total_size,
            "total_files": total_files,
            "formatted_size": formatted_size,
            "trash_path": str(trash_dir),
            "disk_info": {
                "total": disk_total,
                "free": disk_free,
                "used": disk_used,
                "total_formatted": disk_total_formatted,
                "free_formatted": disk_free_formatted,
                "used_formatted": disk_used_formatted,
                "used_percentage": disk_used_percentage,
                "storage_path": str(root_dir)
            }
        })
        
    except Exception as e:
        log_message(f"[Trash] Error getting trash stats: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@trash_bp.route("/clear_trash", methods=["POST"])
def api_clear_trash():
    """Clear all files from trash folder (but keep database records)."""
    try:
        data = request.get_json() or {}
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({"status": "error", "error": "Confirmation required"}), 400
        
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server configuration error"}), 500
        
        trash_dir = root_dir.parent / "Trash"
        
        if not trash_dir.exists():
            return jsonify({
                "status": "ok",
                "message": "Trash folder is already empty",
                "files_deleted": 0,
                "size_freed": 0
            })
        
        # Get stats before deletion
        files_deleted = 0
        size_freed = 0
        
        for file_path in trash_dir.rglob("*"):
            if file_path.is_file():
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    files_deleted += 1
                    size_freed += file_size
                    log_message(f"[Trash] Deleted: {file_path}")
                except (OSError, PermissionError) as e:
                    log_message(f"[Trash] Warning: Could not delete {file_path}: {e}")
                    continue
        
        # Remove empty directories
        try:
            for dir_path in reversed(list(trash_dir.rglob("*"))):
                if dir_path.is_dir() and not list(dir_path.iterdir()):
                    dir_path.rmdir()
                    log_message(f"[Trash] Removed empty directory: {dir_path}")
        except Exception as e:
            log_message(f"[Trash] Warning: Could not remove some empty directories: {e}")
        
        # Update database: mark all deleted tracks as not restorable from file 
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE deleted_tracks
            SET can_restore = 0
            WHERE trash_path IS NOT NULL AND can_restore = 1
        """)
        affected_records = cursor.rowcount
        conn.commit()
        conn.close()
        
        formatted_size = _format_file_size(size_freed)
        
        log_message(f"[Trash] Cleared trash: {files_deleted} files deleted, {formatted_size} freed")
        log_message(f"[Trash] Updated {affected_records} database records (marked as not restorable)")
        
        return jsonify({
            "status": "ok",
            "message": f"Trash cleared successfully",
            "files_deleted": files_deleted,
            "size_freed": size_freed,
            "formatted_size": formatted_size,
            "database_records_updated": affected_records
        })
        
    except Exception as e:
        log_message(f"[Trash] Error clearing trash: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 