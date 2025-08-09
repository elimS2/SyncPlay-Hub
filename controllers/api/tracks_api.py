"""Per-track operations API.

Provides endpoints for resyncing or rescanning media properties of a single track.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from .shared import get_connection, get_root_dir, log_message
import database as db
from utils.media_probe import ffprobe_media_properties


tracks_bp = Blueprint("tracks", __name__)


_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@tracks_bp.route("/track/<video_id>/rescan_media", methods=["POST"])
def api_rescan_track_media(video_id: str):
    """
    Rescan media properties (bitrate, resolution) for a single track.

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

        # Probe media
        duration, bitrate, resolution = ffprobe_media_properties(abs_path)
        size_bytes = abs_path.stat().st_size

        # Determine which fields to update
        fields_updated = []
        update_kwargs = {
            "bitrate": bitrate,
            "resolution": resolution,
        }
        if refresh_duration:
            update_kwargs["duration"] = duration
        if refresh_size:
            update_kwargs["size_bytes"] = size_bytes

        # Filter out None so we do not overwrite with NULL unintentionally
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}

        if update_kwargs:
            db.update_track_media_properties(conn, video_id, **update_kwargs)
            fields_updated = list(update_kwargs.keys())

        log_message(
            f"[Rescan] {video_id} -> updated: {fields_updated or 'none'}; "
            f"bitrate={bitrate}, resolution={resolution}, duration={duration}, size={size_bytes}"
        )

        return jsonify(
            {
                "status": "ok",
                "video_id": video_id,
                "bitrate": bitrate,
                "resolution": resolution,
                "duration": duration,
                "size_bytes": size_bytes,
                "fields_updated": fields_updated,
            }
        )

    except Exception as exc:
        log_message(f"[Rescan] Error for {video_id}: {exc}")
        return jsonify({"status": "error", "error": str(exc)}), 500
    finally:
        conn.close()


