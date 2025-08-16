#!/usr/bin/env python3
"""
Migration 011: Add max_available_height and max_quality_label to youtube_video_metadata

Adds two columns used for server-side filtering/pagination by Max YouTube Quality:
- max_available_height (INTEGER) — maximum video height among available formats
- max_quality_label (TEXT) — display label like '2160p'
"""

import sqlite3
from ..migration_manager import Migration


class Migration011(Migration):
    """Add max_available_height and max_quality_label to youtube_video_metadata."""

    def description(self) -> str:
        return "Add max_available_height (INTEGER) and max_quality_label (TEXT) to youtube_video_metadata"

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(youtube_video_metadata)")
        cols = {row[1] for row in cur.fetchall()}

        if "max_available_height" not in cols:
            cur.execute(
                """
                ALTER TABLE youtube_video_metadata
                ADD COLUMN max_available_height INTEGER
                """
            )

        if "max_quality_label" not in cols:
            cur.execute(
                """
                ALTER TABLE youtube_video_metadata
                ADD COLUMN max_quality_label TEXT
                """
            )

        # Optional: lightweight index for filtering performance
        try:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_ym_max_height ON youtube_video_metadata(max_available_height)"
            )
        except Exception:
            pass

        conn.commit()
        print("✅ Added max_available_height and max_quality_label to youtube_video_metadata")

    def down(self, conn: sqlite3.Connection) -> None:
        # SQLite doesn't support DROP COLUMN easily; safe no-op rollback.
        print("ℹ️ Skipping DROP COLUMN for youtube_video_metadata (not supported by SQLite)")


