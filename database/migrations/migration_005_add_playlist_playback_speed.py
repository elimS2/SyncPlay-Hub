#!/usr/bin/env python3
"""
Migration 005: Add playback speed to playlists table

Adds playback_speed field to store user's preferred playback speed
for each playlist (0.5, 0.75, 1, 1.25, 1.5, 2).
"""

from database.migration_manager import Migration
import sqlite3


class Migration005(Migration):
    """Add playback_speed field to playlists table."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Add playback_speed field to playlists table."""
        
        # Add playback_speed column (default 1.0 = normal speed)
        conn.execute('''
            ALTER TABLE playlists 
            ADD COLUMN playback_speed REAL DEFAULT 1.0
        ''')
        
        # Update existing playlists to have default speed
        conn.execute('''
            UPDATE playlists 
            SET playback_speed = 1.0 
            WHERE playback_speed IS NULL
        ''')
        
        print("✅ Added playback_speed field to playlists table")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove playback_speed field from playlists table."""
        
        # SQLite doesn't support DROP COLUMN, so we need to recreate the table
        conn.execute('''
            CREATE TABLE playlists_backup AS 
            SELECT id, name, relpath, track_count, last_sync_ts, source_url, display_preferences
            FROM playlists
        ''')
        
        conn.execute('DROP TABLE playlists')
        
        conn.execute('''
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                relpath TEXT NOT NULL UNIQUE,
                track_count INTEGER,
                last_sync_ts TEXT,
                source_url TEXT,
                display_preferences TEXT DEFAULT 'shuffle'
            )
        ''')
        
        conn.execute('''
            INSERT INTO playlists (id, name, relpath, track_count, last_sync_ts, source_url, display_preferences)
            SELECT id, name, relpath, track_count, last_sync_ts, source_url, display_preferences
            FROM playlists_backup
        ''')
        
        conn.execute('DROP TABLE playlists_backup')
        
        print("✅ Removed playback_speed field from playlists table")
    
    def description(self) -> str:
        """Migration description."""
        return "Add playback_speed field to playlists table for storing user's preferred playback speed" 