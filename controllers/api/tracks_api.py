"""Per-track operations API.

Provides endpoints for resyncing or rescanning media properties of a single track.
"""

from __future__ import annotations

import re
from pathlib import Path
import json
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from .shared import get_connection, get_root_dir, log_message
import database as db
from utils.media_probe import ffprobe_media_properties, ffprobe_media_properties_ex
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobPriority


tracks_bp = Blueprint("tracks", __name__)


_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@tracks_bp.route("/track/<video_id>/rescan_media", methods=["POST"])
def api_rescan_track_media(video_id: str):
    """
    Rescan media properties (bitrate, resolution) for a single track and
    update extended fields (video_fps, video_codec) when available.

    Request body (optional JSON):
      - refresh_duration: bool (default False)
      - refresh_size: bool (default False)

    Response JSON:
      {
        "status": "ok" | "error",
        "video_id": str,
        "bitrate": int | null,
        "resolution": str | null,
        "duration": float | null,
        "size_bytes": int | null,
        "video_fps": float | null,
        "video_codec": str | null,
        "audio_codec": str | null,
        "audio_bitrate": int | null,
        "audio_sample_rate": int | null,
        "fields_updated": ["bitrate", "resolution", ...],
        "error": str (when status == "error")
      }
    """

    if not _YT_ID_RE.match(video_id or ""):
        return jsonify({"status": "error", "error": "Invalid video_id"}), 400

    root_dir: Path = get_root_dir()
    if not root_dir:
        return jsonify({"status": "error", "error": "Server not initialized"}), 500

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    refresh_duration: bool = bool(payload.get("refresh_duration", False))
    refresh_size: bool = bool(payload.get("refresh_size", False))

    conn = get_connection()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1",
            (video_id,),
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "error": "Track not found"}), 404

        relpath: str = row[0]
        abs_path = (root_dir / relpath).resolve()

        # Ensure path exists and is a file
        if not abs_path.exists() or not abs_path.is_file():
            log_message(f"[Rescan] File not found for {video_id}: {abs_path}")
            return jsonify({"status": "error", "error": "File not found"}), 404

        # Use common utility method for media probing and database update
        from utils.media_probe import rescan_track_media_properties
        
        result = rescan_track_media_properties(
            video_id=video_id,
            file_path=abs_path,
            refresh_duration=refresh_duration,
            refresh_size=refresh_size
        )
        
        if not result["success"]:
            return jsonify({"status": "error", "error": result["error"]}), 500
        
        # Extract results from the utility method
        duration = result["duration"]
        bitrate = result["bitrate"]
        resolution = result["resolution"]
        video_fps = result["video_fps"]
        video_codec = result["video_codec"]
        size_bytes = result["size_bytes"]
        fields_updated = result["fields_updated"]

        return jsonify(
            {
                "status": "ok",
                "video_id": video_id,
                "bitrate": bitrate,
                "resolution": resolution,
                "duration": duration,
                "size_bytes": size_bytes,
                "video_fps": video_fps,
                "video_codec": video_codec,
                "audio_codec": result.get("audio_codec"),
                "audio_bitrate": result.get("audio_bitrate"),
                "audio_sample_rate": result.get("audio_sample_rate"),
                "audio_bitrate_estimated": bool(result.get("audio_bitrate_estimated", False)),
                "fields_updated": fields_updated,
            }
        )

    except Exception as exc:
        log_message(f"[Rescan] Error for {video_id}: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500
    finally:
        conn.close()



@tracks_bp.route("/track/<video_id>/rescan_youtube_metadata", methods=["POST"])
def api_rescan_youtube_metadata(video_id: str):
    """Enqueue a Single Video Metadata Extraction job for a given video.

    Request JSON (optional):
      - force_update: bool (default True)

    Response JSON:
      { status: 'started' | 'error', job_id?: int, error?: str }
    """
    if not _YT_ID_RE.match(video_id or ""):
        return jsonify({"status": "error", "error": "Invalid video_id"}), 400

    data = request.get_json(silent=True) or {}
    force_update = bool(data.get("force_update", True))

    try:
        job_service = get_job_queue_service()
        job_id = job_service.create_and_add_job(
            JobType.SINGLE_VIDEO_METADATA_EXTRACTION,
            priority=JobPriority.NORMAL,
            video_id=video_id,
            force_update=force_update,
        )
        log_message(f"[YouTubeRescan] Enqueued SINGLE_VIDEO_METADATA_EXTRACTION for {video_id} as job #{job_id}")
        return jsonify({"status": "started", "job_id": job_id})
    except Exception as exc:
        log_message(f"[YouTubeRescan] Failed to enqueue for {video_id}: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500


@tracks_bp.route("/track/<video_id>/youtube_formats", methods=["GET"])
def api_get_youtube_formats(video_id: str):
    """Return available YouTube formats and summary stored in DB for a video.

    Response JSON on success:
      {
        status: 'ok',
        video_id: str,
        available_formats: list | null,      # parsed from JSON TEXT
        available_qualities_summary: str | null,
        updated_at: str | null
      }
    """
    if not _YT_ID_RE.match(video_id or ""):
        return jsonify({"status": "error", "error": "Invalid video_id"}), 400

    conn = get_connection()
    try:
        row = db.get_youtube_metadata_by_id(conn, video_id)
        if not row:
            return jsonify({
                "status": "ok",
                "video_id": video_id,
                "available_formats": None,
                "available_qualities_summary": None,
                "updated_at": None,
            })

        # Parse JSON TEXT field available_formats safely
        row_dict = dict(row)
        raw_formats = row_dict.get("available_formats")
        try:
            parsed_formats = json.loads(raw_formats) if raw_formats else None
        except Exception:
            parsed_formats = None

        return jsonify({
            "status": "ok",
            "video_id": video_id,
            "available_formats": parsed_formats,
            "available_qualities_summary": row_dict.get("available_qualities_summary"),
            "updated_at": row_dict.get("updated_at"),
        })
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500
    finally:
        conn.close()


@tracks_bp.route("/track/<video_id>/redownload", methods=["POST"])
def api_redownload_track_in_quality(video_id: str):
    """Redownload a single video in a selected quality and replace the local file.

    Request JSON:
      - format_id: str (optional)  e.g., '137' for 1080p mp4
      - format_selector: str (optional) yt-dlp -f expression; overrides format_id
      - audio_only: bool (optional, default False)

    Strategy:
      - Derive target_folder from current track relpath (keep same directory)
      - Enqueue SINGLE_VIDEO_DOWNLOAD with force_overwrites + ignore_archive
      - Pass video_id for post-processing
    """
    if not _YT_ID_RE.match(video_id or ""):
        return jsonify({"status": "error", "error": "Invalid video_id"}), 400

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    requested_format_id = (payload.get("format_id") or "").strip()
    explicit_selector = (payload.get("format_selector") or "").strip()
    audio_only = bool(payload.get("audio_only", False))
    prefer_mp4 = bool(payload.get("prefer_mp4", True))
    target_height = int(payload.get("target_height", 1080))

    # Locate current folder
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1",
            (video_id,),
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "error": "Track not found"}), 404

        relpath: str = row[0]
    finally:
        conn.close()

    # Derive target folder relative to Playlists root
    try:
        root_dir: Path = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server not initialized"}), 500
        abs_path = (root_dir / relpath).resolve()
        # Use parent folder name relative to Playlists
        try:
            target_folder = str(abs_path.parent.relative_to(root_dir)).replace("\\", "/")
        except ValueError:
            target_folder = ""  # fallback to default 'SingleVideos' in worker
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500

    # Build format selector
    if explicit_selector:
        format_selector = explicit_selector
    else:
        if audio_only:
            format_selector = "bestaudio/best"
        else:
            # Prefer MP4/H.264 video + AAC audio at target height, fallback chain without recode
            # Order: exact height avc1 mp4 + m4a -> 137+140 (1080p) -> <=target_height avc1 mp4 + m4a -> best[ext=mp4]
            preferred = (
                f"bestvideo[ext=mp4][vcodec*=avc1][height={target_height}]+bestaudio[ext=m4a]/"
                f"137+140/"
                f"bestvideo[ext=mp4][vcodec*=avc1][height<={target_height}]+bestaudio[ext=m4a]/"
                f"best[ext=mp4]"
            )
            if requested_format_id:
                format_selector = f"{requested_format_id}+bestaudio[ext=m4a]/" + preferred
            else:
                format_selector = preferred

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Enqueue job
    try:
        job_service = get_job_queue_service()
        job_id = job_service.create_and_add_job(
            JobType.SINGLE_VIDEO_DOWNLOAD,
            priority=JobPriority.HIGH,
            playlist_url=video_url,
            target_folder=target_folder,
            format_selector=format_selector,
            extract_audio=audio_only,
            download_archive=True,
            ignore_archive=True,      # force redownload
            force_overwrites=True,    # replace existing file
            cleanup_old_variants=True, # custom hint for worker
            skip_full_scan=True,       # optimize DB update for single video
            prefer_mp4=prefer_mp4,
            target_height=target_height,
            video_id=video_id,
        )
        log_message(
            f"[Redownload] Enqueued SINGLE_VIDEO_DOWNLOAD for {video_id} as job #{job_id}; "
            f"target='{target_folder}', format='{format_selector}', audio_only={audio_only}"
        )
        return jsonify({"status": "started", "job_id": job_id})
    except Exception as exc:
        log_message(f"[Redownload] Failed to enqueue for {video_id}: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500
