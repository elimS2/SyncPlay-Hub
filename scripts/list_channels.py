#!/usr/bin/env python3
"""
List Channels

Simple utility to list all channels and groups with their IDs for easy reference.

Usage:
    python scripts/list_channels.py
    python scripts/list_channels.py --group-only
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database import get_connection


def list_channel_groups(conn):
    """List all channel groups."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, behavior_type, 
               COUNT(c.id) as channel_count,
               COALESCE(SUM(c.track_count), 0) as total_tracks
        FROM channel_groups cg
        LEFT JOIN channels c ON c.channel_group_id = cg.id AND c.enabled = 1
        GROUP BY cg.id, cg.name, cg.behavior_type
        ORDER BY cg.name
    """)
    
    groups = cur.fetchall()
    
    print("📁 CHANNEL GROUPS:")
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
    
    print("\n📺 CHANNELS:")
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
            print(f"\n   📁 Group: {group_name}")
            print("   " + "-" * 75)
        
        # Status icon
        status_icon = "✅" if enabled else "❌"
        
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
    python scripts/list_channels.py            # List all groups and channels
    python scripts/list_channels.py --groups-only  # List only groups
        """
    )
    
    parser.add_argument(
        "--groups-only",
        action="store_true",
        help="Show only channel groups, not individual channels"
    )
    
    args = parser.parse_args()
    
    try:
        conn = get_connection()
        
        # List groups
        groups = list_channel_groups(conn)
        
        # List channels if requested
        if not args.groups_only:
            list_channels(conn)
        
        print("\n" + "=" * 80)
        print("💡 Usage tips:")
        print("   • Use channel IDs with: python scripts/channel_download_analyzer.py --channel-id ID")
        print("   • Use group IDs with: python scripts/channel_download_analyzer.py --group-id ID")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 