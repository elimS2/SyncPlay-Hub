#!/usr/bin/env python3
"""
Migration 008: Add available YouTube formats storage

Adds two columns to youtube_video_metadata to store normalized formats and a
compact summary for UI rendering:
- available_formats (TEXT) — JSON-serialized list of normalized formats
- available_qualities_summary (TEXT) — human-readable compact summary
"""

from database.migration_manager import Migration
import sqlite3


class Migration008(Migration):
    """Add available formats and summary to youtube_video_metadata."""

    def description(self) -> str:
        return "Add available_formats and available_qualities_summary to youtube_video_metadata"

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        # Check existing columns
        cur.execute("PRAGMA table_info(youtube_video_metadata)")
        cols = {row[1] for row in cur.fetchall()}

        if "available_formats" not in cols:
            cur.execute(
                """
                ALTER TABLE youtube_video_metadata
                ADD COLUMN available_formats TEXT
                """
            )

        if "available_qualities_summary" not in cols:
            cur.execute(
                """
                ALTER TABLE youtube_video_metadata
                ADD COLUMN available_qualities_summary TEXT
                """
            )

        conn.commit()
        print("✅ Added available_formats and available_qualities_summary columns to youtube_video_metadata")

    def down(self, conn: sqlite3.Connection) -> None:
        # SQLite doesn't support DROP COLUMN directly; a full table rebuild would be required.
        # For simplicity and safety, we leave columns in place on rollback.
        print("ℹ️ Skipping DROP COLUMN for youtube_video_metadata (not supported by SQLite)")


