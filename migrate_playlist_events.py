#!/usr/bin/env python3
"""
Playlist Events Migration Script

This script creates playlist_added events for all existing track-playlist
associations in the database. This is needed because playlist addition
logging was implemented after tracks were already in the database.

Usage:
    python migrate_playlist_events.py [--dry-run] [--db-path PATH]

Options:
    --dry-run    Show what would be migrated without actually doing it
    --db-path    Path to database file (default: ./music_library.db)
"""

import argparse
import os
import sys
from database import get_connection, migrate_existing_playlist_associations, set_db_path

print("🚀 Migration script starting...")


def main():
    parser = argparse.ArgumentParser(description='Migrate existing playlist associations to events')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be migrated without actually doing it')
    parser.add_argument('--db-path', default=r'D:\music\Youtube\DB\tracks.db',
                       help='Path to database file (default: D:\\music\\Youtube\\DB\\tracks.db)')
    
    args = parser.parse_args()
    
    # Check if database exists
    if not os.path.exists(args.db_path):
        print(f"❌ Database file not found: {args.db_path}")
        print("Make sure you're in the correct directory and the database exists.")
        sys.exit(1)
    
    print("🔄 Playlist Events Migration")
    print("=" * 50)
    print(f"Database: {args.db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    print()
    
    try:
        # Set database path and connect
        print(f"🔗 Setting database path: {args.db_path}")
        set_db_path(args.db_path)
        print("📡 Connecting to database...")
        conn = get_connection()
        print("✅ Database connection successful")
        
        # Run migration
        print("🔍 Analyzing track-playlist associations...")
        result = migrate_existing_playlist_associations(conn, dry_run=args.dry_run)
        
        # Display results
        if result['dry_run']:
            print(f"📊 Migration Analysis:")
            print(f"   Total track-playlist associations: {result['total_associations']}")
            print(f"   Would create events for: {result['would_migrate']}")
            print()
            if result['total_associations'] == 0:
                print("ℹ️  No track-playlist associations found in database")
                print("   This could mean:")
                print("   - Database is empty (no tracks scanned yet)")
                print("   - No playlists have been processed")
                print("   - Database schema needs to be updated")
                print()
                print("💡 Try running: python scan_to_db.py --root <your-data-root>")
            else:
                print("✅ Dry run completed successfully!")
                print("💡 Run without --dry-run to perform actual migration")
        else:
            print(f"📊 Migration Results:")
            print(f"   Total associations: {result['total_associations']}")
            print(f"   Successfully migrated: {result['migrated']}")
            print(f"   Success rate: {result['migrated']/result['total_associations']*100:.1f}%")
            print()
            print("✅ Migration completed successfully!")
            print("📂 All existing playlist associations now have corresponding events")
            print("🔍 Check history page to see migrated events with source='migration'")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 