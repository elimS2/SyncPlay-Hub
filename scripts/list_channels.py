#!/usr/bin/env python3
"""
List Channels

Simple utility to list all channels and groups with their IDs for easy reference.

Usage:
    python scripts/list_channels.py
    python scripts/list_channels.py --group-only
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection, set_db_path

# Try to load .env file manually
def load_env_file():
    """Load .env file manually and return config dict."""
    env_path = Path(__file__).parent.parent / '.env'
    config = {}
    
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove BOM if present
                        key = key.strip().lstrip('\ufeff')
                        config[key] = value.strip()
            print(f"[INFO] Loaded .env file from: {env_path}")
        except Exception as e:
            print(f"[WARNING] Error reading .env file: {e}")
    
    return config

# Load .env configuration
env_config = load_env_file()


def list_channel_groups(conn):
    """List all channel groups."""
    cur = conn.cursor()
    cur.execute("""
        SELECT cg.id, cg.name, cg.behavior_type, 
               COUNT(c.id) as channel_count,
               COALESCE(SUM(c.track_count), 0) as total_tracks
        FROM channel_groups cg
        LEFT JOIN channels c ON c.channel_group_id = cg.id AND c.enabled = 1
        GROUP BY cg.id, cg.name, cg.behavior_type
        ORDER BY cg.name
    """)
    
    groups = cur.fetchall()
    
    print("[CHANNEL GROUPS]")
    print("=" * 80)
    
    if not groups:
        print("   No channel groups found.")
        return []
    
    for group in groups:
        group_id, name, behavior_type, channel_count, total_tracks = group
        print(f"   ID: {group_id:2} | {name:20} | {behavior_type:10} | {channel_count:2} channels | {total_tracks:4} tracks")
    
    return [dict(group) for group in groups]


def list_channels(conn, group_id=None):
    """List all channels or channels in specific group."""
    cur = conn.cursor()
    
    if group_id:
        cur.execute("""
            SELECT c.id, c.name, c.url, c.track_count, c.enabled, c.last_sync_ts,
                   cg.name as group_name
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
            WHERE c.channel_group_id = ?
            ORDER BY c.name
        """, (group_id,))
    else:
        cur.execute("""
            SELECT c.id, c.name, c.url, c.track_count, c.enabled, c.last_sync_ts,
                   cg.name as group_name
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
            ORDER BY cg.name, c.name
        """)
    
    channels = cur.fetchall()
    
    print("\n[CHANNELS]")
    print("=" * 80)
    
    if not channels:
        print("   No channels found.")
        return
    
    current_group = None
    for channel in channels:
        channel_id, name, url, track_count, enabled, last_sync, group_name = channel
        
        # Print group header if changed
        if group_name != current_group:
            current_group = group_name
            print(f"\n   Group: {group_name}")
            print("   " + "-" * 75)
        
        # Status icon
        status_icon = "[ACTIVE]" if enabled else "[DISABLED]"
        
        # Format track count
        tracks_str = f"{track_count or 0:4} tracks" if track_count else "   0 tracks"
        
        # Format last sync
        sync_str = last_sync[:10] if last_sync else "Never"
        
        print(f"   {status_icon} ID: {channel_id:2} | {name:25} | {tracks_str} | Sync: {sync_str}")
        print(f"      URL: {url}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="List channels and groups with their IDs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/list_channels.py                                    # List all groups and channels
    python scripts/list_channels.py --groups-only                      # List only groups
    python scripts/list_channels.py --db-path "D:/music/Youtube/DB/tracks.db"  # Use specific database
    
.env file variables:
    DB_PATH         Path to the database file (e.g., D:/music/Youtube/DB/tracks.db)
        """
    )
    
    parser.add_argument(
        "--groups-only",
        action="store_true",
        help="Show only channel groups, not individual channels"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to the database file (overrides .env file)"
    )
    
    args = parser.parse_args()
    
    # Set database path from command line argument or .env file
    db_path = args.db_path
    if not db_path:
        db_path = env_config.get('DB_PATH')
    
    if db_path:
        # Check if path exists
        db_file = Path(db_path)
        if db_file.exists():
            set_db_path(db_path)
            print(f"[INFO] Using database: {db_path}")
        else:
            print(f"[WARNING] Database file not found: {db_path}")
            print(f"[INFO] Using default database: tracks.db (current directory)")
    else:
        print(f"[INFO] Using default database: tracks.db (current directory)")
        print(f"[HINT] Set DB_PATH in .env file or use --db-path to specify database location")
    
    try:
        conn = get_connection()
        
        # List groups
        groups = list_channel_groups(conn)
        
        # List channels if requested
        if not args.groups_only:
            list_channels(conn)
        
        print("\n" + "=" * 80)
        print("[USAGE TIPS]")
        print("   • Use channel IDs with: python scripts/channel_download_analyzer.py --channel-id ID")
        print("   • Use group IDs with: python scripts/channel_download_analyzer.py --group-id ID")
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 