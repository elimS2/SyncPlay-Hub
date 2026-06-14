#!/usr/bin/env python3
"""
Migration013 - Add track_count_updated_at to channels table
"""

import sqlite3
from database.migration_manager import Migration


class Migration013(Migration):
    def description(self) -> str:
        return "Add track_count_updated_at column to channels for persisted track count freshness"

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(channels)")
        cols = {row[1] for row in cur.fetchall()}
        if "track_count_updated_at" not in cols:
            cur.execute("ALTER TABLE channels ADD COLUMN track_count_updated_at TEXT")

    def down(self, conn: sqlite3.Connection) -> None:
        pass
