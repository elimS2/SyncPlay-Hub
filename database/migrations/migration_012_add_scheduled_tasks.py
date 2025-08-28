#!/usr/bin/env python3
"""
Migration012 - Add scheduled_tasks table for recurring scheduler
"""

import sqlite3
from database.migration_manager import Migration


class Migration012(Migration):
    def description(self) -> str:
        return "Add scheduled_tasks table to support recurring task scheduler"

    def up(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()

        # Create scheduled_tasks table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                schedule_kind TEXT NOT NULL,
                schedule_time TEXT NULL,
                schedule_days TEXT NULL,
                interval_minutes INTEGER NULL,
                cron_expr TEXT NULL,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                params_json TEXT NOT NULL,
                last_run_at TEXT NULL,
                next_run_at TEXT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # Basic index to speed lookups on enabled tasks
        try:
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_enabled
                ON scheduled_tasks (enabled)
                """
            )
        except Exception:
            pass

        # Update trigger for updated_at
        try:
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_scheduled_tasks_updated_at
                AFTER UPDATE ON scheduled_tasks
                BEGIN
                    UPDATE scheduled_tasks
                    SET updated_at = datetime('now')
                    WHERE id = NEW.id;
                END;
                """
            )
        except Exception:
            pass

        conn.commit()

    def down(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        # Drop trigger first
        try:
            cur.execute("DROP TRIGGER IF EXISTS trg_scheduled_tasks_updated_at")
        except Exception:
            pass
        # Drop table
        cur.execute("DROP TABLE IF EXISTS scheduled_tasks")
        conn.commit()


