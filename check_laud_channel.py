#!/usr/bin/env python3
import sqlite3
from pathlib import Path

# Database path
db_path = "D:/music/Youtube/DB/tracks.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== CHECKING LAUD CHANNEL ===")
    
    # Check channels table
    print("\n1. Checking channels table:")
    cursor.execute("SELECT * FROM channels WHERE url LIKE '%LAUD%' OR name LIKE '%LAUD%'")
    channels = cursor.fetchall()
    if channels:
        for channel in channels:
            print(f"   Found channel: {channel}")
    else:
        print("   No LAUD channel found in channels table")
    
    # Check channel_groups table 
    print("\n2. Checking channel_groups table:")
    cursor.execute("SELECT * FROM channel_groups")
    groups = cursor.fetchall()
    for group in groups:
        print(f"   Group: {group}")
    
    # Check tracks table structure first
    print("\n3. Checking tracks table structure:")
    cursor.execute("PRAGMA table_info(tracks)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   Column: {col}")
    
    # Check tracks table for LAUD content
    print("\n4. Checking tracks table for LAUD content:")
    cursor.execute("SELECT COUNT(*) FROM tracks WHERE channel_group = 'New Music'")
    track_count = cursor.fetchone()[0]
    print(f"   Tracks in 'New Music' group: {track_count}")
    
    # Check recent tracks using correct column name
    cursor.execute("SELECT relpath, title, channel_group FROM tracks WHERE channel_group = 'New Music' ORDER BY id DESC LIMIT 5")
    recent_tracks = cursor.fetchall()
    if recent_tracks:
        print("   Recent tracks:")
        for track in recent_tracks:
            print(f"     - {track[1]} ({track[0]})")
    else:
        print("   No tracks found in 'New Music' group")
    
    # Check all tracks to see if any were downloaded
    cursor.execute("SELECT COUNT(*) FROM tracks")
    total_tracks = cursor.fetchone()[0]
    print(f"   Total tracks in database: {total_tracks}")
    
    # Check events table for channel activity
    print("\n5. Checking events table for channel activity:")
    cursor.execute("SELECT * FROM events WHERE event_type = 'channel_added' ORDER BY timestamp DESC LIMIT 3")
    events = cursor.fetchall()
    if events:
        print("   Recent channel events:")
        for event in events:
            print(f"     - {event}")
    
    # Check if download completed but not recorded
    print("\n6. Checking if files exist in folder:")
    import os
    laud_folder = Path("D:/music/Youtube/Playlists/New Music/Channel-LAUD")
    if laud_folder.exists():
        files = list(laud_folder.glob("*.mp4"))
        print(f"   Found {len(files)} files in {laud_folder}")
        if files:
            print("   Sample files:")
            for f in files[:3]:
                print(f"     - {f.name}")
    else:
        print(f"   Folder doesn't exist: {laud_folder}")
    
    conn.close()
    print("\n=== CHECK COMPLETE ===")
    
except Exception as e:
    print(f"Error checking database: {e}") 