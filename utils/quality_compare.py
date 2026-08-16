#!/usr/bin/env python3
"""Compare local file quality against the best available YouTube height."""

from __future__ import annotations

from typing import Any, Dict, Optional

AUDIO_FILETYPES = frozenset({"mp3", "m4a", "opus", "flac", "ogg", "wav", "aac"})
HEIGHT_SLACK_PX = 16

# Conservative bits-per-second floors used only when local resolution is missing.
# A file clearly under these values is treated as below the YouTube max height.
BITRATE_FLOOR_BY_HEIGHT = (
    (2160, 3_200_000),
    (1440, 1_600_000),
    (1080, 800_000),
    (720, 400_000),
    (0, 150_000),
)


def parse_local_height(resolution: Any) -> Optional[int]:
    """Parse height from a stored resolution like '1920x1080'."""
    if resolution is None:
        return None
    raw = str(resolution).strip().lower()
    if not raw:
        return None
    if "x" in raw:
        right = raw.split("x", 1)[1]
        digits = ""
        for char in right:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            height = int(digits)
            return height if height > 0 else None
    if raw.endswith("p") and raw[:-1].isdigit():
        height = int(raw[:-1])
        return height if height > 0 else None
    return None


def is_audio_filetype(filetype: Any) -> bool:
    return str(filetype or "").strip().lower() in AUDIO_FILETYPES


def is_below_max_by_height(local_height: Any, max_height: Any, slack_px: int = HEIGHT_SLACK_PX) -> bool:
    """True when the local file height is clearly below YouTube max height."""
    try:
        local_value = int(local_height)
        max_value = int(max_height)
    except (TypeError, ValueError):
        return False
    if local_value <= 0 or max_value <= 0:
        return False
    return local_value + int(slack_px) < max_value


def bitrate_floor_for_max_height(max_height: Any) -> Optional[int]:
    try:
        max_value = int(max_height)
    except (TypeError, ValueError):
        return None
    if max_value <= 0:
        return None
    for height, floor in BITRATE_FLOOR_BY_HEIGHT:
        if max_value >= height:
            return floor
    return None


def estimated_bitrate_bps(size_bytes: Any, duration_seconds: Any) -> Optional[float]:
    try:
        size_value = float(size_bytes)
        duration_value = float(duration_seconds)
    except (TypeError, ValueError):
        return None
    if size_value <= 0 or duration_value <= 0:
        return None
    return size_value * 8.0 / duration_value


def is_below_max_by_bitrate(size_bytes: Any, duration_seconds: Any, max_height: Any) -> bool:
    """Fallback when resolution is missing: tiny files vs a high YouTube max."""
    floor = bitrate_floor_for_max_height(max_height)
    bitrate = estimated_bitrate_bps(size_bytes, duration_seconds)
    if floor is None or bitrate is None:
        return False
    return bitrate < floor


def classify_local_vs_youtube_quality(
    resolution: Any,
    filetype: Any,
    size_bytes: Any,
    track_duration: Any,
    yvm_duration: Any,
    max_height: Any,
) -> str:
    """Return below_height, below_bitrate, at_max, unknown, or audio."""
    if is_audio_filetype(filetype):
        return "audio"
    local_height = parse_local_height(resolution)
    if local_height is not None:
        if is_below_max_by_height(local_height, max_height):
            return "below_height"
        return "at_max"
    duration = track_duration if track_duration else yvm_duration
    if is_below_max_by_bitrate(size_bytes, duration, max_height):
        return "below_bitrate"
    return "unknown"


def _iter_quality_rows(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.video_id,
            t.name,
            t.relpath,
            t.resolution,
            t.filetype,
            t.size_bytes,
            t.duration,
            yvm.duration,
            yvm.max_available_height
        FROM tracks t
        JOIN youtube_video_metadata yvm ON yvm.youtube_id = t.video_id
        WHERE t.video_id NOT IN (
            SELECT dt.video_id FROM deleted_tracks dt
            WHERE dt.restored_at IS NULL
        )
        AND yvm.max_available_height IS NOT NULL
        ORDER BY t.id ASC
        """
    )
    return cur.fetchall()


def count_tracks_below_max_youtube_quality(conn) -> Dict[str, int]:
    """Count non-deleted video tracks downloaded below YouTube max quality.

    Height comparison is preferred. When local resolution is missing, a
    conservative size/duration heuristic is used so unprobed low-quality
    files (like a 36 MB 4K-capable video) are still counted.
    """
    below_by_height = 0
    below_by_bitrate = 0
    at_or_above = 0
    unknown_local = 0

    for row in _iter_quality_rows(conn):
        _video_id, _name, _relpath, resolution, filetype, size_bytes, track_duration, yvm_duration, max_height = row
        kind = classify_local_vs_youtube_quality(
            resolution, filetype, size_bytes, track_duration, yvm_duration, max_height
        )
        if kind == "below_height":
            below_by_height += 1
        elif kind == "below_bitrate":
            below_by_bitrate += 1
        elif kind == "at_max":
            at_or_above += 1
        elif kind == "unknown":
            unknown_local += 1

    below_total = below_by_height + below_by_bitrate
    return {
        "tracks_below_max_quality": below_total,
        "tracks_below_max_quality_by_height": below_by_height,
        "tracks_below_max_quality_by_bitrate": below_by_bitrate,
        "tracks_at_max_quality": at_or_above,
        "tracks_unknown_local_quality": unknown_local,
    }


def list_tracks_below_max_youtube_quality(conn, limit: Optional[int] = None) -> list[Dict[str, Any]]:
    """Return below-max video tracks that are candidates for a safe quality upgrade."""
    tracks: list[Dict[str, Any]] = []
    for row in _iter_quality_rows(conn):
        video_id, name, relpath, resolution, filetype, size_bytes, track_duration, yvm_duration, max_height = row
        kind = classify_local_vs_youtube_quality(
            resolution, filetype, size_bytes, track_duration, yvm_duration, max_height
        )
        if kind not in {"below_height", "below_bitrate"}:
            continue
        tracks.append(
            {
                "video_id": video_id,
                "name": name,
                "relpath": relpath,
                "resolution": resolution,
                "filetype": filetype,
                "size_bytes": size_bytes,
                "max_available_height": max_height,
                "reason": kind,
            }
        )
        if isinstance(limit, int) and limit > 0 and len(tracks) >= limit:
            break
    return tracks
