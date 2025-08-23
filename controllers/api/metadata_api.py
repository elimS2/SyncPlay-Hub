"""
Metadata API endpoints for managing YouTube video metadata.
"""

from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message
import database as db

# Create blueprint
metadata_bp = Blueprint('metadata', __name__)


@metadata_bp.route("/scan_missing_metadata", methods=["POST"])
def api_scan_missing_metadata():
    """Scan for tracks missing metadata and create extraction jobs."""
    try:
        data = request.get_json() or {}
        limit = data.get('limit')  # Optional limit
        force_update = data.get('force_update', False)  # Force update all
        dry_run = data.get('dry_run', False)  # Just show what would be done
        
        log_message(f"[Metadata API] Starting metadata scan - limit: {limit}, force_update: {force_update}, dry_run: {dry_run}")
        
        # Get database connection
        conn = get_connection()
        
        # Find tracks missing metadata (using logic from scan_missing_metadata.py)
        def find_tracks_missing_metadata(conn, limit=None, force_update=False):
            """Find tracks that are missing YouTube metadata."""
            try:
                cur = conn.cursor()
                
                if force_update:
                    # Force update mode: get all non-deleted tracks
                    query = """
                    SELECT t.id, t.video_id, t.name, t.published_date
                    FROM tracks t
                    WHERE t.video_id NOT IN (
                        SELECT dt.video_id FROM deleted_tracks dt
                        WHERE dt.restored_at IS NULL
                    )
                    ORDER BY t.id ASC
                    """
                    params = []
                else:
                    # Normal mode: find tracks without metadata or with incomplete metadata
                    query = """
                    SELECT t.id, t.video_id, t.name, t.published_date
                    FROM tracks t
                    LEFT JOIN youtube_video_metadata yvm ON t.video_id = yvm.youtube_id
                    WHERE t.video_id NOT IN (
                        SELECT dt.video_id FROM deleted_tracks dt
                        WHERE dt.restored_at IS NULL
                    )
                    AND (
                        yvm.youtube_id IS NULL 
                        OR (yvm.timestamp IS NULL AND yvm.release_timestamp IS NULL)
                    )
                    ORDER BY t.id ASC
                    """
                    params = []
                
                # Add limit if specified
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                
                cur.execute(query, params)
                results = cur.fetchall()
                
                # Convert to list of dictionaries
                tracks = []
                for row in results:
                    track = {
                        'id': row[0],
                        'video_id': row[1],
                        'name': row[2],
                        'published_date': row[3]
                    }
                    tracks.append(track)
                
                return tracks
                
            except Exception as e:
                log_message(f"[Metadata API] Error finding tracks missing metadata: {e}")
                return []
        
        # Get metadata statistics
        def get_metadata_statistics(conn):
            """Get statistics about metadata coverage."""
            try:
                cur = conn.cursor()
                
                # Total non-deleted tracks
                cur.execute("""
                    SELECT COUNT(*) FROM tracks t
                    WHERE t.video_id NOT IN (
                        SELECT dt.video_id FROM deleted_tracks dt
                        WHERE dt.restored_at IS NULL
                    )
                """)
                total_tracks = cur.fetchone()[0]
                
                # Tracks with metadata
                cur.execute("""
                    SELECT COUNT(*) FROM tracks t
                    JOIN youtube_video_metadata yvm ON t.video_id = yvm.youtube_id
                    WHERE t.video_id NOT IN (
                        SELECT dt.video_id FROM deleted_tracks dt
                        WHERE dt.restored_at IS NULL
                    )
                    AND (yvm.timestamp IS NOT NULL OR yvm.release_timestamp IS NOT NULL)
                """)
                tracks_with_metadata = cur.fetchone()[0]
                
                # Tracks without metadata
                tracks_without_metadata = total_tracks - tracks_with_metadata
                
                # Coverage percentage
                coverage_percent = (tracks_with_metadata / total_tracks * 100) if total_tracks > 0 else 0
                
                return {
                    'total_tracks': total_tracks,
                    'tracks_with_metadata': tracks_with_metadata,
                    'tracks_without_metadata': tracks_without_metadata,
                    'coverage_percent': coverage_percent
                }
                
            except Exception as e:
                log_message(f"[Metadata API] Error getting metadata statistics: {e}")
                return {
                    'total_tracks': 0,
                    'tracks_with_metadata': 0,
                    'tracks_without_metadata': 0,
                    'coverage_percent': 0
                }
        
        # Get statistics
        stats = get_metadata_statistics(conn)
        
        # Find tracks missing metadata
        tracks = find_tracks_missing_metadata(conn, limit, force_update)
        
        conn.close()
        
        if dry_run:
            # Just return what would be done
            return jsonify({
                "status": "preview",
                "message": f"Found {len(tracks)} tracks missing metadata",
                "statistics": stats,
                "tracks_found": len(tracks),
                "would_create_jobs": len(tracks),
                "sample_tracks": tracks[:5] if tracks else [],
                "process": "dry_run"
            })
        
        # Create metadata extraction jobs
        if not tracks:
            return jsonify({
                "status": "up_to_date",
                "message": "All tracks already have metadata",
                "statistics": stats,
                "tracks_found": 0,
                "jobs_created": 0
            })
        
        try:
            from services.job_queue_service import get_job_queue_service
            from services.job_types import JobType, JobPriority
            
            # Get job service
            job_service = get_job_queue_service()
            
            jobs_created = 0
            jobs_failed = 0
            
            for track in tracks:
                try:
                    # Create job for this track
                    job_id = job_service.create_and_add_job(
                        JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
                        priority=JobPriority.LOW,  # Low priority for batch processing
                        video_id=track['video_id'],
                        force_update=force_update
                    )
                    
                    jobs_created += 1
                    
                except Exception as e:
                    jobs_failed += 1
                    log_message(f"[Metadata API] Failed to create job for track {track['video_id']}: {e}")
            
            log_message(f"[Metadata API] Created {jobs_created} metadata extraction jobs for tracks missing metadata")
            
            return jsonify({
                "status": "started",
                "message": f"Created {jobs_created} metadata extraction jobs",
                "statistics": stats,
                "tracks_found": len(tracks),
                "jobs_created": jobs_created,
                "jobs_failed": jobs_failed,
                "process": "job_queue"
            })
            
        except ImportError:
            # Fallback if job queue not available
            log_message(f"[Metadata API] Job Queue System not available")
            
            return jsonify({
                "status": "error",
                "error": "Job Queue System not available. Use scripts/scan_missing_metadata.py instead.",
                "statistics": stats,
                "tracks_found": len(tracks),
                "fallback_command": f"python scripts/scan_missing_metadata.py --limit {limit or 'unlimited'}"
            }), 500
        
    except Exception as e:
        log_message(f"[Metadata API] Error during metadata scan: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@metadata_bp.route("/scan_missing_youtube_qualities", methods=["POST"])
def api_scan_missing_youtube_qualities():
    """Find tracks missing YouTube Qualities and enqueue single-video metadata extraction jobs.

    Request JSON (optional):
      - limit: int (max number of tracks to process)
      - force_update: bool (default True) – enforce refresh even if metadata exists
      - dry_run: bool (default False) – preview without creating jobs

    Behavior:
      - Looks for tracks not marked deleted.
      - Missing qualities criteria:
          yvm.youtube_id IS NULL OR
          yvm.available_formats IS NULL OR TRIM(yvm.available_formats) = '' OR
          yvm.max_available_height IS NULL
    """
    try:
        data = request.get_json(silent=True) or {}
        limit = data.get('limit')
        force_update = bool(data.get('force_update', True))
        dry_run = bool(data.get('dry_run', False))

        log_message(f"[Metadata API] Scan missing YouTube Qualities – limit={limit}, force_update={force_update}, dry_run={dry_run}")

        conn = get_connection()
        cur = conn.cursor()

        sql = (
            """
            SELECT t.id, t.video_id, t.name
            FROM tracks t
            LEFT JOIN youtube_video_metadata yvm ON yvm.youtube_id = t.video_id
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
                WHERE dt.restored_at IS NULL
            )
            AND (
                yvm.youtube_id IS NULL OR
                yvm.available_formats IS NULL OR TRIM(yvm.available_formats) = '' OR
                yvm.max_available_height IS NULL
            )
            ORDER BY t.id ASC
            """
        )
        params = []
        if isinstance(limit, int):
            sql += " LIMIT ?"
            params.append(int(limit))

        rows = cur.execute(sql, params).fetchall()
        tracks = [{"id": r[0], "video_id": r[1], "name": r[2]} for r in rows]
        conn.close()

        if dry_run:
            return jsonify({
                "status": "preview",
                "tracks_found": len(tracks),
                "sample_tracks": tracks[:10],
            })

        if not tracks:
            return jsonify({
                "status": "up_to_date",
                "message": "No tracks missing YouTube Qualities found",
                "tracks_found": 0,
                "jobs_created": 0,
            })

        try:
            from services.job_queue_service import get_job_queue_service
            from services.job_types import JobType, JobPriority

            job_service = get_job_queue_service()
            jobs_created = 0
            jobs_failed = 0

            for tr in tracks:
                try:
                    job_id = job_service.create_and_add_job(
                        JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
                        priority=JobPriority.HIGH,
                        video_id=tr['video_id'],
                        force_update=force_update,
                    )
                    jobs_created += 1
                except Exception as e:
                    jobs_failed += 1
                    log_message(f"[Qualities Scan] Failed to enqueue for {tr['video_id']}: {e}")

            return jsonify({
                "status": "started",
                "message": f"Created {jobs_created} extraction jobs",
                "tracks_found": len(tracks),
                "jobs_created": jobs_created,
                "jobs_failed": jobs_failed,
            })

        except ImportError:
            return jsonify({
                "status": "error",
                "error": "Job Queue System not available",
                "tracks_found": len(tracks),
            }), 500

    except Exception as e:
        log_message(f"[Metadata API] Error during qualities scan: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@metadata_bp.route("/metadata_statistics", methods=["GET"])
def api_metadata_statistics():
    """Get metadata coverage statistics."""
    try:
        conn = get_connection()
        
        # Get overall statistics
        cur = conn.cursor()
        
        # Total non-deleted tracks
        cur.execute("""
            SELECT COUNT(*) FROM tracks t
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
                WHERE dt.restored_at IS NULL
            )
        """)
        total_tracks = cur.fetchone()[0]
        
        # Tracks with metadata
        cur.execute("""
            SELECT COUNT(*) FROM tracks t
            JOIN youtube_video_metadata yvm ON t.video_id = yvm.youtube_id
            WHERE t.video_id NOT IN (
                SELECT dt.video_id FROM deleted_tracks dt
                WHERE dt.restored_at IS NULL
            )
            AND (yvm.timestamp IS NOT NULL OR yvm.release_timestamp IS NOT NULL)
        """)
        tracks_with_metadata = cur.fetchone()[0]
        
        # Tracks without metadata
        tracks_without_metadata = total_tracks - tracks_with_metadata
        
        # Coverage percentage
        coverage_percent = (tracks_with_metadata / total_tracks * 100) if total_tracks > 0 else 0
        
        # Recent metadata additions
        cur.execute("""
            SELECT COUNT(*) FROM youtube_video_metadata 
            WHERE created_at >= datetime('now', '-7 days')
        """)
        recent_additions = cur.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "statistics": {
                "total_tracks": total_tracks,
                "tracks_with_metadata": tracks_with_metadata,
                "tracks_without_metadata": tracks_without_metadata,
                "coverage_percent": round(coverage_percent, 1),
                "recent_additions": recent_additions
            }
        })
        
    except Exception as e:
        log_message(f"[Metadata API] Error getting metadata statistics: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 