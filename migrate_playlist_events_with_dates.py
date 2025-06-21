#!/usr/bin/env python3
"""
Playlist Events Migration Script with File Creation Dates

This script updates existing playlist_added events to use file creation dates
instead of migration timestamp, providing more accurate historical timeline.

Usage:
    python migrate_playlist_events_with_dates.py [--dry-run] [--db-path PATH]

Options:
    --dry-run    Show what would be updated without actually doing it
    --db-path    Path to database file (default: D:\music\Youtube\DB\tracks.db)
"""

import argparse
import os
import sys
import sqlite3
from pathlib import Path
import datetime
from database import get_connection, set_db_path

print("🚀 Playlist Events Date Migration script starting...")

def get_file_creation_date(file_path: Path) -> str:
    """Get file creation date in SQLite datetime format.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Creation date in 'YYYY-MM-DD HH:MM:SS' format or None if file not found
    """
    try:
        if file_path.exists():
            stat = file_path.stat()
            created = datetime.datetime.fromtimestamp(stat.st_ctime)
            return created.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return None
    except Exception as e:
        print(f"Error getting file date for {file_path}: {e}")
        return None


def update_playlist_events_with_file_dates(conn: sqlite3.Connection, dry_run: bool = False):
    """Update existing playlist_added events with file creation dates.
    
    Args:
        conn: Database connection
        dry_run: If True, only show what would be updated without actually doing it
        
    Returns:
        dict with update statistics
    """
    cur = conn.cursor()
    
    # Get all playlist_added events with source='migration'
    cur.execute("""
        SELECT ph.id, ph.video_id, t.relpath, ph.ts as current_ts
        FROM play_history ph
        JOIN tracks t ON t.video_id = ph.video_id
        WHERE ph.event = 'playlist_added' 
        AND ph.additional_data LIKE '%source:migration%'
        ORDER BY ph.id
    """)
    
    events = cur.fetchall()
    total_events = len(events)
    
    if total_events == 0:
        return {
            'total_events': 0,
            'updated': 0,
            'file_not_found': 0,
            'dry_run': dry_run
        }
    
    print(f"📊 Found {total_events} playlist_added events with source='migration'")
    
    if dry_run:
        print("🔍 DRY RUN - Analyzing file dates...")
    else:
        print("🔄 Updating events with file creation dates...")
    
    # Base path for media files
    base_path = Path(r"D:\music\Youtube\Playlists")
    
    updated_count = 0
    file_not_found_count = 0
    
    for i, (event_id, video_id, relpath, current_ts) in enumerate(events, 1):
        # Construct full file path
        file_path = base_path / relpath
        
        # Get file creation date
        file_date = get_file_creation_date(file_path)
        
        if file_date:
            if dry_run:
                print(f"   Event {event_id}: {video_id} -> {current_ts} → {file_date}")
            else:
                # Update the event timestamp
                try:
                    cur.execute(
                        "UPDATE play_history SET ts = ? WHERE id = ?",
                        (file_date, event_id)
                    )
                    updated_count += 1
                    if i % 100 == 0:  # Progress indicator
                        print(f"   Processed {i}/{total_events} events...")
                except Exception as e:
                    print(f"   ❌ Error updating event {event_id}: {e}")
        else:
            print(f"   ⚠️  File not found: {file_path}")
            file_not_found_count += 1
    
    if not dry_run:
        print(f"💾 Committing {updated_count} updates to database...")
        conn.commit()
        print("✅ Database commit successful")
    
    return {
        'total_events': total_events,
        'updated': updated_count,
        'file_not_found': file_not_found_count,
        'dry_run': dry_run
    }


def main():
    parser = argparse.ArgumentParser(description='Update playlist events with file creation dates')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be updated without actually doing it')
    parser.add_argument('--db-path', default=r'D:\music\Youtube\DB\tracks.db',
                       help='Path to database file (default: D:\\music\\Youtube\\DB\\tracks.db)')
    
    args = parser.parse_args()
    
    # Check if database exists
    if not os.path.exists(args.db_path):
        print(f"❌ Database file not found: {args.db_path}")
        print("Make sure you're in the correct directory and the database exists.")
        sys.exit(1)
    
    print("🔄 Playlist Events Date Migration")
    print("=" * 50)
    print(f"Database: {args.db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print()
    
    try:
        # Set database path and connect
        print(f"🔗 Setting database path: {args.db_path}")
        set_db_path(args.db_path)
        print("📡 Connecting to database...")
        conn = get_connection()
        print("✅ Database connection successful")
        
        # Run update
        print("🔍 Analyzing playlist_added events...")
        result = update_playlist_events_with_file_dates(conn, dry_run=args.dry_run)
        
        # Display results
        print()
        if result['dry_run']:
            print(f"📊 Update Analysis:")
            print(f"   Total playlist_added events (migration): {result['total_events']}")
            print(f"   Would update with file dates: {result['updated']}")
            print(f"   Files not found: {result['file_not_found']}")
            print()
            if result['total_events'] == 0:
                print("ℹ️  No migration events found to update")
                print("   Run the original migration first if needed")
            else:
                print("✅ Dry run completed successfully!")
                print("💡 Run without --dry-run to perform actual update")
        else:
            print(f"📊 Update Results:")
            print(f"   Total events processed: {result['total_events']}")
            print(f"   Successfully updated: {result['updated']}")
            print(f"   Files not found: {result['file_not_found']}")
            success_rate = (result['updated'] / result['total_events'] * 100) if result['total_events'] > 0 else 0
            print(f"   Success rate: {success_rate:.1f}%")
            print()
            print("✅ Date migration completed successfully!")
            print("📅 Playlist events now use file creation dates")
            print("🔍 Check history page to see updated timeline")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 