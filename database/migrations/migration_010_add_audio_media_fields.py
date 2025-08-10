#!/usr/bin/env python3
"""
Migration 010: Add audio media fields to tracks

Adds columns to persist audio stream properties (for audio-only files and
video files with audio tracks):
- audio_codec (TEXT) — audio codec short name from ffprobe (e.g., aac, opus)
- audio_bitrate (INTEGER) — audio bitrate in bits per second (bps)
- audio_sample_rate (INTEGER) — audio sample rate in Hz (e.g., 44100, 48000)
"""

from database.migration_manager import Migration
import sqlite3


class Migration010(Migration):
    """Add audio_codec, audio_bitrate, audio_sample_rate to tracks table."""

    def description(self) -> str:
        return (
            "Add audio media fields (audio_codec TEXT, audio_bitrate INTEGER, "
            "audio_sample_rate INTEGER) to tracks table"
        )

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()

        # Check existing columns on tracks
        cur.execute("PRAGMA table_info(tracks)")
        cols = {row[1] for row in cur.fetchall()}

        if "audio_codec" not in cols:
            cur.execute(
                """
                ALTER TABLE tracks
                ADD COLUMN audio_codec TEXT
                """
            )

        if "audio_bitrate" not in cols:
            cur.execute(
                """
                ALTER TABLE tracks
                ADD COLUMN audio_bitrate INTEGER
                """
            )

        if "audio_sample_rate" not in cols:
            cur.execute(
                """
                ALTER TABLE tracks
                ADD COLUMN audio_sample_rate INTEGER
                """
            )

        conn.commit()
        print("✅ Added audio_codec, audio_bitrate, audio_sample_rate columns to tracks")

    def down(self, conn: sqlite3.Connection) -> None:
        # SQLite does not support DROP COLUMN directly. For safety, skip removal.
        print("ℹ️ Skipping DROP COLUMN for tracks (SQLite limitation)")


