"""
Database package for YouTube downloader project.

Contains migration system and database management utilities.
"""

# Export main classes for convenience
from .migration_manager import MigrationManager, Migration

# Import and export functions from database.py (root file)
import importlib.util
import sys
from pathlib import Path

# Path to database.py file in project root
database_py_path = Path(__file__).parent.parent / "database.py"

# Load database.py module as database_core
spec = importlib.util.spec_from_file_location("database_core", database_py_path)
database_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database_core)

# Export functions from database_core
# Connection helpers
set_db_path = database_core.set_db_path
get_connection = database_core.get_connection

# Playlist management
upsert_playlist = database_core.upsert_playlist
update_playlist_stats = database_core.update_playlist_stats
get_playlist_by_relpath = database_core.get_playlist_by_relpath

# Track management
upsert_track = database_core.upsert_track
link_track_playlist = database_core.link_track_playlist
iter_tracks_with_playlists = database_core.iter_tracks_with_playlists
increment_play = database_core.increment_play

# Event recording
record_event = database_core.record_event
record_volume_change = database_core.record_volume_change
record_seek_event = database_core.record_seek_event
record_playlist_addition = database_core.record_playlist_addition

# History and playback
iter_history = database_core.iter_history
get_history_page = database_core.get_history_page

# Backup functionality
create_backup = database_core.create_backup
list_backups = database_core.list_backups

# User settings
get_user_setting = database_core.get_user_setting
set_user_setting = database_core.set_user_setting
get_user_volume = database_core.get_user_volume
set_user_volume = database_core.set_user_volume

# Channel management
create_channel_group = database_core.create_channel_group
get_channel_groups = database_core.get_channel_groups
get_channel_group_by_id = database_core.get_channel_group_by_id
update_channel_group = database_core.update_channel_group
delete_channel_group = database_core.delete_channel_group
create_channel = database_core.create_channel
get_channels_by_group = database_core.get_channels_by_group
get_channel_by_url = database_core.get_channel_by_url
get_channel_by_id = database_core.get_channel_by_id
update_channel_sync = database_core.update_channel_sync
record_channel_added = database_core.record_channel_added
record_channel_synced = database_core.record_channel_synced

# Deleted tracks management
record_track_deletion = database_core.record_track_deletion
get_deleted_tracks = database_core.get_deleted_tracks
restore_deleted_track = database_core.restore_deleted_track
should_auto_delete_track = database_core.should_auto_delete_track

# YouTube metadata
upsert_youtube_metadata = database_core.upsert_youtube_metadata
get_youtube_metadata_by_id = database_core.get_youtube_metadata_by_id
get_youtube_metadata_by_playlist = database_core.get_youtube_metadata_by_playlist
delete_youtube_metadata = database_core.delete_youtube_metadata
search_youtube_metadata = database_core.search_youtube_metadata
get_youtube_metadata_stats = database_core.get_youtube_metadata_stats

# Migration utilities
migrate_existing_playlist_associations = database_core.migrate_existing_playlist_associations

__all__ = [
    # Migration classes
    'MigrationManager', 
    'Migration',
    
    # Connection helpers
    'set_db_path',
    'get_connection',
    
    # Playlist management
    'upsert_playlist',
    'update_playlist_stats',
    'get_playlist_by_relpath',
    
    # Track management
    'upsert_track',
    'link_track_playlist',
    'iter_tracks_with_playlists',
    'increment_play',
    
    # Event recording
    'record_event',
    'record_volume_change',
    'record_seek_event',
    'record_playlist_addition',
    
    # History and playback
    'iter_history',
    'get_history_page',
    
    # Backup functionality
    'create_backup',
    'list_backups',
    
    # User settings
    'get_user_setting',
    'set_user_setting',
    'get_user_volume',
    'set_user_volume',
    
    # Channel management
    'create_channel_group',
    'get_channel_groups',
    'get_channel_group_by_id',
    'create_channel',
    'get_channels_by_group',
    'get_channel_by_url',
    'get_channel_by_id',
    'update_channel_sync',
    'record_channel_added',
    'record_channel_synced',
    
    # Deleted tracks management
    'record_track_deletion',
    'get_deleted_tracks',
    'restore_deleted_track',
    'should_auto_delete_track',
    
    # YouTube metadata
    'upsert_youtube_metadata',
    'get_youtube_metadata_by_id',
    'get_youtube_metadata_by_playlist',
    'delete_youtube_metadata',
    'search_youtube_metadata',
    'get_youtube_metadata_stats',
    
    # Migration utilities
    'migrate_existing_playlist_associations',
] 