#!/usr/bin/env python3
"""
Migration 006: Add virtual playlist preferences table

Creates a separate table to store preferences for virtual playlists
that don't exist in the main playlists table.
"""

from database.migration_manager import Migration
import sqlite3


class Migration006(Migration):
    """Add virtual playlist preferences table."""
    
    def description(self) -> str:
        """Migration description."""
        return "Add virtual playlist preferences table for storing preferences of virtual playlists"
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Create virtual_playlist_preferences table."""
        
        # Create table for virtual playlist preferences
        conn.execute('''
            CREATE TABLE IF NOT EXISTS virtual_playlist_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relpath TEXT UNIQUE NOT NULL,
                display_preferences TEXT DEFAULT 'smart',
                playback_speed REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster lookups
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_virtual_playlist_relpath 
            ON virtual_playlist_preferences(relpath)
        ''')
        
        print("✅ Created virtual_playlist_preferences table")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Drop virtual_playlist_preferences table."""
        
        conn.execute('DROP TABLE IF EXISTS virtual_playlist_preferences')
        print("✅ Dropped virtual_playlist_preferences table") 