#!/usr/bin/env python3
"""
Migration 007: Add layout preference to playlists and virtual playlists

Adds layout_preference field to store user's preferred playlist layout
for each playlist (hidden, under_video, side_by_side).
"""

from database.migration_manager import Migration
import sqlite3


class Migration007(Migration):
    """Add layout_preference field to playlists and virtual_playlist_preferences tables."""
    
    def description(self) -> str:
        """Migration description."""
        return "Add layout_preference field to playlists and virtual_playlist_preferences tables for storing user's preferred playlist layout"
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Add layout_preference field to playlists and virtual_playlist_preferences tables."""
        
        # Add layout_preference column to playlists table (default side_by_side)
        conn.execute('''
            ALTER TABLE playlists 
            ADD COLUMN layout_preference TEXT DEFAULT 'side_by_side'
        ''')
        
        # Update existing playlists to have default layout preference
        conn.execute('''
            UPDATE playlists 
            SET layout_preference = 'side_by_side' 
            WHERE layout_preference IS NULL
        ''')
        
        # Add layout_preference column to virtual_playlist_preferences table (default side_by_side)
        conn.execute('''
            ALTER TABLE virtual_playlist_preferences 
            ADD COLUMN layout_preference TEXT DEFAULT 'side_by_side'
        ''')
        
        # Update existing virtual playlist preferences to have default layout preference
        conn.execute('''
            UPDATE virtual_playlist_preferences 
            SET layout_preference = 'side_by_side' 
            WHERE layout_preference IS NULL
        ''')
        
        print("✅ Added layout_preference field to playlists and virtual_playlist_preferences tables")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove layout_preference field from playlists and virtual_playlist_preferences tables."""
        
        # SQLite doesn't support DROP COLUMN, so we need to recreate the playlists table
        conn.execute('''
            CREATE TABLE playlists_backup AS 
            SELECT id, name, relpath, track_count, last_sync_ts, source_url, display_preferences, playback_speed
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
                display_preferences TEXT DEFAULT 'shuffle',
                playback_speed REAL DEFAULT 1.0
            )
        ''')
        
        conn.execute('''
            INSERT INTO playlists (id, name, relpath, track_count, last_sync_ts, source_url, display_preferences, playback_speed)
            SELECT id, name, relpath, track_count, last_sync_ts, source_url, display_preferences, playback_speed
            FROM playlists_backup
        ''')
        
        conn.execute('DROP TABLE playlists_backup')
        
        # For virtual_playlist_preferences, we can't easily drop columns, so we'll just leave it
        # The field will be ignored in future operations
        print("✅ Removed layout_preference field from playlists table (virtual_playlist_preferences field preserved)") 