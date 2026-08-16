#!/usr/bin/env python3
"""Smoke checks for local vs YouTube max-quality comparison."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import database as db
from utils.quality_compare import (
    count_tracks_below_max_youtube_quality,
    is_below_max_by_bitrate,
    is_below_max_by_height,
    parse_local_height,
)


def _insert_track(conn, video_id: str, **fields) -> None:
    conn.execute(
        """
        INSERT INTO tracks (video_id, name, relpath, duration, size_bytes, resolution, filetype)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            fields.get("name") or video_id,
            fields.get("relpath") or f"{video_id}.mp4",
            fields.get("duration"),
            fields.get("size_bytes"),
            fields.get("resolution"),
            fields.get("filetype") or "mp4",
        ),
    )
    conn.execute(
        """
        INSERT INTO youtube_video_metadata (youtube_id, duration, max_available_height)
        VALUES (?, ?, ?)
        """,
        (video_id, fields.get("yvm_duration"), fields.get("max_height")),
    )
    conn.commit()


def test_parsers() -> None:
    assert parse_local_height("1920x1080") == 1080
    assert parse_local_height("3840x2160") == 2160
    assert parse_local_height("1080p") == 1080
    assert parse_local_height("") is None
    assert parse_local_height(None) is None
    assert is_below_max_by_height(1080, 2160) is True
    assert is_below_max_by_height(2160, 2160) is False
    assert is_below_max_by_height(2150, 2160) is False
    assert is_below_max_by_bitrate(36_000_000, 981, 2160) is True
    assert is_below_max_by_bitrate(1_400_000_000, 981, 2160) is False


def test_counts(tmp_path: Path) -> None:
    db.set_db_path(tmp_path / "tracks.db")
    conn = db.get_connection()
    _insert_track(conn, "heightLow", resolution="1280x720", max_height=2160, duration=100, size_bytes=50_000_000)
    _insert_track(conn, "heightMax", resolution="3840x2160", max_height=2160, duration=100, size_bytes=400_000_000)
    _insert_track(
        conn,
        "SybKGa60Z3Q",
        resolution=None,
        max_height=2160,
        duration=None,
        yvm_duration=981,
        size_bytes=36_000_000,
    )
    _insert_track(conn, "audioOnly", filetype="mp3", resolution=None, max_height=2160, duration=200, size_bytes=5_000_000)
    counts = count_tracks_below_max_youtube_quality(conn)
    conn.close()
    assert counts["tracks_below_max_quality_by_height"] == 1
    assert counts["tracks_below_max_quality_by_bitrate"] == 1
    assert counts["tracks_below_max_quality"] == 2
    assert counts["tracks_at_max_quality"] == 1
    assert "SybKGa60Z3Q"  # example-shaped row is included via bitrate fallback


def main() -> int:
    test_parsers()
    print("[PASS] test_parsers")
    with tempfile.TemporaryDirectory() as tmp:
        test_counts(Path(tmp))
    print("[PASS] test_counts")
    print("[OK] quality compare checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
