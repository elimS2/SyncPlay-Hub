#!/usr/bin/env python3
"""
Script to update channel statistics based on actual files in folders.
"""

import sqlite3
from pathlib import Path

def update_channel_stats():
    """Update channel track counts based on actual files."""
    
    # Database connection
    db_path = "D:/music/Youtube/DB/tracks.db"
    playlists_path = Path("D:/music/Youtube/Playlists")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=== Updating Channel Statistics ===")
        
        # Get all channels
        cursor.execute("""
            SELECT c.id, c.name, c.url, cg.name as group_name
            FROM channels c
            JOIN channel_groups cg ON cg.id = c.channel_group_id
        """)
        
        channels = cursor.fetchall()
        
        for channel_id, channel_name, channel_url, group_name in channels:
            print(f"\nChecking channel: {channel_name} in group '{group_name}'")
            
            # Find channel folder
            channel_folder = playlists_path / group_name / f"Channel-{channel_name}"
            
            track_count = 0
            if channel_folder.exists():
                # Count video files
                video_extensions = ['.mp4', '.webm', '.mkv', '.avi']
                video_files = [f for f in channel_folder.iterdir() 
                              if f.is_file() and f.suffix.lower() in video_extensions]
                track_count = len(video_files)
                
                print(f"  Folder: {channel_folder}")
                print(f"  Found {track_count} video files")
                
                # Show some sample files
                if video_files:
                    print("  Sample files:")
                    for f in video_files[:3]:
                        print(f"    - {f.name}")
                    if len(video_files) > 3:
                        print(f"    ... and {len(video_files) - 3} more")
            else:
                print(f"  Folder not found: {channel_folder}")
            
            # Update database
            cursor.execute("""
                UPDATE channels 
                SET track_count = ?, last_sync_ts = datetime('now')
                WHERE id = ?
            """, (track_count, channel_id))
            
            print(f"  Updated database: {track_count} tracks")
        
        conn.commit()
        conn.close()
        
        print("\n✅ Channel statistics updated successfully!")
        print("Refresh the /channels page to see updated counts.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_channel_stats() 