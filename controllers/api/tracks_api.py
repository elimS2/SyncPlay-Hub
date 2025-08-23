"""Per-track operations API.

Provides endpoints for resyncing or rescanning media properties of a single track.
"""

from __future__ import annotations

import re
from pathlib import Path
import json
from typing import Any, Dict

from flask import Blueprint, jsonify, request, send_file, current_app

from .shared import get_connection, get_root_dir, get_thumbnails_dir, log_message
import database as db
from utils.media_probe import ffprobe_media_properties, ffprobe_media_properties_ex
from services.job_queue_service import get_job_queue_service
from services.job_types import JobType, JobPriority
import subprocess
import os
import tempfile
from glob import glob


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


@tracks_bp.route("/track/<video_id>/preview.jpg", methods=["GET"])
def api_video_preview_image(video_id: str):
    """Return a generated JPEG preview (first frame) for the specified video.

    Query params:
      - w: target width (int, default 480)
      - t: timestamp in seconds for the frame (float, default 1.0)

    Uses on-disk cache under static/cache/thumbs. Cache is invalidated when
    source media mtime is newer than cached image.
    """
    try:
        if not _YT_ID_RE.match(video_id or ""):
            return jsonify({"status": "error", "error": "Invalid video_id"}), 400

        # Resolve media path from DB
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server not initialized"}), 500

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1",
                (video_id,),
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "error": "Track not found"}), 404
            relpath = row[0]
        finally:
            conn.close()

        src_path = (root_dir / relpath).resolve()
        if not src_path.exists() or not src_path.is_file():
            return jsonify({"status": "error", "error": "File not found"}), 404

        try:
            width = int(request.args.get("w", 480))
            if width < 64:
                width = 64
            if width > 1920:
                width = 1920
        except Exception:
            width = 480
        try:
            timestamp = float(request.args.get("t", 1.0))
            if timestamp < 0:
                timestamp = 0.0
        except Exception:
            timestamp = 1.0

        # Cache path incorporates source mtime and width
        try:
            src_mtime = int(src_path.stat().st_mtime)
        except Exception:
            src_mtime = 0
        cache_dir = (Path(current_app.root_path) / "static" / "cache" / "thumbs").resolve()
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception:
            pass
        cache_name = f"{video_id}_{width}_{src_mtime}.jpg"
        cache_path = cache_dir / cache_name

        if cache_path.exists():
            try:
                return send_file(str(cache_path), mimetype="image/jpeg", max_age=3600)
            except Exception:
                # fall through to regenerate
                pass

        # Generate with ffmpeg
        # -ss before -i for faster seek, -frames:v 1 for single frame, scale width keep AR (use -2 for mod2)
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".jpg")
        os.close(tmp_fd)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            str(timestamp),
            "-i",
            str(src_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2:flags=bicubic",
            "-q:v",
            "2",
            "-y",
            tmp_name,
        ]
        try:
            subprocess.run(cmd, check=True)
            # Move atomically into cache
            try:
                os.replace(tmp_name, cache_path)
            except Exception:
                # If cannot move, just send temp file without caching
                return send_file(tmp_name, mimetype="image/jpeg")
            return send_file(str(cache_path), mimetype="image/jpeg", max_age=3600)
        except Exception as exc:
            try:
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
            except Exception:
                pass
            return jsonify({"status": "error", "error": f"ffmpeg failed: {exc}"}), 500
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


def _get_previews_dir() -> Path:
    base = Path(current_app.root_path) / "static" / "previews"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base


def _find_adjacent_thumbnail(root_dir: Path, relpath: str, video_id: str) -> Path | None:
    """Search only in the media file's parent directory for a YouTube thumbnail like *[VIDEO_ID].webp/jpg/png."""
    try:
        import re as _re
        media_abs = (root_dir / relpath).resolve()
        parent = media_abs.parent
        pattern = _re.compile(r"\\[" + _re.escape(video_id) + r"\\]")
        for p in parent.iterdir():
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {".webp", ".jpg", ".jpeg", ".png"}:
                    continue
                if pattern.search(p.stem):
                    return p
            except Exception:
                continue
    except Exception:
        return None
    return None


def _find_in_thumbnails_dir(video_id: str) -> Path | None:
    """If THUMBNAILS_DIR is configured, search there for files named *[VIDEO_ID].webp/jpg/png or <video_id>_*.png."""
    try:
        import re as _re
        tdir = get_thumbnails_dir()
        if not tdir:
            return None
        p = Path(tdir)
        if not p.exists() or not p.is_dir():
            return None
        # Prefer explicit centralized names first
        preferred = [
            p / f"{video_id}_manual.png",
            p / f"{video_id}_from_youtube.png",
            p / f"{video_id}_from_media_file.png",
        ]
        for cand in preferred:
            if cand.exists() and cand.is_file():
                return cand
        # Otherwise scan for legacy downloaded thumbnails with [VIDEO_ID]
        pattern = _re.compile(r"\\[" + _re.escape(video_id) + r"\\]")
        for fp in p.iterdir():
            try:
                if not fp.is_file():
                    continue
                if fp.suffix.lower() not in {".webp", ".jpg", ".jpeg", ".png"}:
                    continue
                if pattern.search(fp.stem):
                    return fp
            except Exception:
                continue
    except Exception:
        return None
    return None


def _ensure_from_youtube_png(previews_dir: Path, src_image: Path, video_id: str) -> Path | None:
    """Convert/copy found thumbnail to centralized PNG path and return it."""
    out_path = previews_dir / f"{video_id}_from_youtube.png"
    # If already exists, return
    if out_path.exists():
        return out_path
    # Try convert with ffmpeg (handles webp/jpg/png to png)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(src_image),
        "-vf",
        "scale=640:-2:flags=bicubic",
        "-q:v",
        "2",
        "-y",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True)
        return out_path if out_path.exists() else None
    except Exception:
        try:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _ensure_from_media_png(previews_dir: Path, src_media: Path, video_id: str, timestamp: float = 1.0, width: int = 640) -> Path | None:
    out_path = previews_dir / f"{video_id}_from_media_file.png"
    if out_path.exists():
        return out_path
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        str(timestamp),
        "-i",
        str(src_media),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2:flags=bicubic",
        "-q:v",
        "2",
        "-y",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True)
        return out_path if out_path.exists() else None
    except Exception:
        try:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


@tracks_bp.route("/track/<video_id>/preview.png", methods=["GET"])
def api_central_preview_png(video_id: str):
    """Serve centralized preview PNG from static/previews with priority:
    manual -> from_youtube -> from_media_file. If none exist, attempt to
    create from YouTube thumbnail (adjacent .webp/.jpg) or extract from media.
    """
    try:
        if not _YT_ID_RE.match(video_id or ""):
            return jsonify({"status": "error", "error": "Invalid video_id"}), 400

        # Choose output directory: THUMBNAILS_DIR if configured, else static/previews
        configured_tdir = get_thumbnails_dir()
        if configured_tdir:
            previews_dir = Path(configured_tdir)
            try:
                previews_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            previews_dir = _get_previews_dir()
        manual = previews_dir / f"{video_id}_manual.png"
        from_youtube = previews_dir / f"{video_id}_from_youtube.png"
        from_media = previews_dir / f"{video_id}_from_media_file.png"

        # Optional refresh: force re-generate from source
        force_refresh = str(request.args.get("refresh", "0")).lower() in {"1", "true", "yes"}
        if force_refresh:
            try:
                if from_youtube.exists():
                    from_youtube.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                if from_media.exists():
                    from_media.unlink(missing_ok=True)
            except Exception:
                pass

        # 1) manual
        if manual.exists():
            return send_file(str(manual), mimetype="image/png", max_age=0)

        # 2) from_youtube (existing)
        if from_youtube.exists():
            return send_file(str(from_youtube), mimetype="image/png", max_age=0)

        # 3) from_media (existing)
        if from_media.exists():
            return send_file(str(from_media), mimetype="image/png", max_age=0)

        # Resolve media path from DB
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server not initialized"}), 500
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1",
                (video_id,),
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "error": "Track not found"}), 404
            relpath = row[0]
        finally:
            conn.close()

        # Try thumbnails dir first (if configured) for an existing image
        adj = _find_in_thumbnails_dir(video_id)
        if not adj:
            # Try adjacent thumbnail conversion on demand
            adj = _find_adjacent_thumbnail(root_dir, relpath, video_id)
        if adj and adj.exists():
            conv = _ensure_from_youtube_png(previews_dir, adj, video_id)
            if conv and conv.exists():
                return send_file(str(conv), mimetype="image/png", max_age=0)

        # Fallback: extract first frame from media
        media_abs = (root_dir / relpath).resolve()
        gen = _ensure_from_media_png(previews_dir, media_abs, video_id, timestamp=1.0, width=640)
        if gen and gen.exists():
            return send_file(str(gen), mimetype="image/png", max_age=0)

        return jsonify({"status": "error", "error": "Failed to create preview"}), 500
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


@tracks_bp.route("/track/<video_id>/preview_info", methods=["GET"])
def api_preview_info(video_id: str):
    """Return JSON describing which preview will be served and its absolute path.

    Query params:
      - refresh: 1|true to clear cached generated files (from_youtube/from_media).
    """
    try:
        if not _YT_ID_RE.match(video_id or ""):
            return jsonify({"status": "error", "error": "Invalid video_id"}), 400

        configured_tdir = get_thumbnails_dir()
        if configured_tdir:
            previews_dir = Path(configured_tdir)
            try:
                previews_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            previews_dir = _get_previews_dir()

        manual = previews_dir / f"{video_id}_manual.png"
        from_youtube = previews_dir / f"{video_id}_from_youtube.png"
        from_media = previews_dir / f"{video_id}_from_media_file.png"

        # Optional refresh toggles
        force_refresh = str(request.args.get("refresh", "0")).lower() in {"1", "true", "yes"}
        if force_refresh:
            try:
                if from_youtube.exists():
                    from_youtube.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                if from_media.exists():
                    from_media.unlink(missing_ok=True)
            except Exception:
                pass

        # Resolve media relpath
        root_dir = get_root_dir()
        if not root_dir:
            return jsonify({"status": "error", "error": "Server not initialized"}), 500
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT relpath FROM tracks WHERE video_id = ? LIMIT 1",
                (video_id,),
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "error": "Track not found"}), 404
            relpath = row[0]
        finally:
            conn.close()

        # Decision tree (same as preview.png): manual -> from_youtube -> from_media
        if manual.exists():
            return jsonify({"status": "ok", "source": "manual", "path": str(manual)})

        if from_youtube.exists():
            return jsonify({"status": "ok", "source": "from_youtube", "path": str(from_youtube)})

        if from_media.exists():
            return jsonify({"status": "ok", "source": "from_media_file", "path": str(from_media)})

        # Try find adjacent or in thumbnails dir and convert
        adj = _find_in_thumbnails_dir(video_id) or _find_adjacent_thumbnail(root_dir, relpath, video_id)
        if adj and adj.exists():
            conv = _ensure_from_youtube_png(previews_dir, adj, video_id)
            if conv and conv.exists():
                return jsonify({"status": "ok", "source": "from_youtube", "path": str(conv)})

        # Fallback generate from media
        media_abs = (root_dir / relpath).resolve()
        gen = _ensure_from_media_png(previews_dir, media_abs, video_id, timestamp=1.0, width=640)
        if gen and gen.exists():
            return jsonify({"status": "ok", "source": "from_media_file", "path": str(gen)})

        return jsonify({"status": "error", "error": "Failed to resolve preview"}), 500
    except Exception as exc:
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
