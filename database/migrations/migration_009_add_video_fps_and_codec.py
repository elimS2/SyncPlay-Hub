#!/usr/bin/env python3
"""
Migration 009: Add video_fps and video_codec to tracks

Adds two columns to tracks table to persist local media video properties:
- video_fps (REAL) — frame rate in frames per second (may be fractional, e.g., 29.97)
- video_codec (TEXT) — codec short name from ffprobe (e.g., h264, hevc, vp9, av1)
"""

from database.migration_manager import Migration
import sqlite3


class Migration009(Migration):
    """Add video_fps (REAL) and video_codec (TEXT) to tracks table."""

    def description(self) -> str:
        return "Add video_fps (REAL) and video_codec (TEXT) columns to tracks table"

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()

        # Check existing columns on tracks
        cur.execute("PRAGMA table_info(tracks)")
        cols = {row[1] for row in cur.fetchall()}

        if "video_fps" not in cols:
            cur.execute(
                """
                ALTER TABLE tracks
                ADD COLUMN video_fps REAL
                """
            )

        if "video_codec" not in cols:
            cur.execute(
                """
                ALTER TABLE tracks
                ADD COLUMN video_codec TEXT
                """
            )

        conn.commit()
        print("✅ Added video_fps (REAL) and video_codec (TEXT) columns to tracks")

    def down(self, conn: sqlite3.Connection) -> None:
        # SQLite does not support DROP COLUMN directly. A full table rebuild would be required.
        # For safety, we do not attempt to remove columns on rollback.
        print("ℹ️ Skipping DROP COLUMN for tracks (SQLite limitation)")


