#!/usr/bin/env python3
"""
Migration 004: Add display preferences to playlists table

Adds display_preferences field to store user's preferred view mode
for each playlist (shuffle, smart, order_by_date).
"""

from database.migration_manager import Migration
import sqlite3


class Migration004(Migration):
    """Add display_preferences field to playlists table."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Add display_preferences field to playlists table."""
        
        # Add display_preferences column
        conn.execute('''
            ALTER TABLE playlists 
            ADD COLUMN display_preferences TEXT DEFAULT 'shuffle'
        ''')
        
        # Update existing playlists to have default preference
        conn.execute('''
            UPDATE playlists 
            SET display_preferences = 'shuffle' 
            WHERE display_preferences IS NULL
        ''')
        
        print("✅ Added display_preferences field to playlists table")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Remove display_preferences field from playlists table."""
        
        # SQLite doesn't support DROP COLUMN, so we need to recreate the table
        conn.execute('''
            CREATE TABLE playlists_backup AS 
            SELECT id, name, relpath, track_count, last_sync_ts, source_url 
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
                source_url TEXT
            )
        ''')
        
        conn.execute('''
            INSERT INTO playlists (id, name, relpath, track_count, last_sync_ts, source_url)
            SELECT id, name, relpath, track_count, last_sync_ts, source_url
            FROM playlists_backup
        ''')
        
        conn.execute('DROP TABLE playlists_backup')
        
        print("✅ Removed display_preferences field from playlists table")
    
    def description(self) -> str:
        """Migration description."""
        return "Add display_preferences field to playlists table for storing user's preferred view mode" 