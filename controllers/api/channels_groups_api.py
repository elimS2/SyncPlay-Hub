"""Channel Groups API endpoints."""

import re
import threading
import shutil
import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event
import database as db

# Create blueprint
channels_groups_bp = Blueprint('channels_groups', __name__)

@channels_groups_bp.route("/channel_groups")
def api_get_channel_groups():
    """Get all channel groups with statistics."""
    try:
        conn = get_connection()
        groups = db.get_channel_groups(conn)
        conn.close()
        
        # Augment with actual playlist (on-disk) track counts to reflect what the player shows
        try:
            root_dir = get_root_dir()
        except Exception:
            root_dir = None
        # Short-lived cache to avoid repeated disk scans within a small window
        if root_dir:
            import time
            media_exts = {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
            try:
                # Lazy in-memory cache on the function object
                cache = getattr(api_get_channel_groups, "_playlist_counts_cache", {})
                cache_ts = getattr(api_get_channel_groups, "_playlist_counts_cache_ts", 0.0)
                ttl_seconds = 15.0  # very short TTL to minimize staleness
                now = time.time()
                # Allow force refresh via query param
                force_refresh = (request.args.get('refresh') == '1')
                if force_refresh or not cache or (now - cache_ts) > ttl_seconds:
                    new_cache = {}
                    for g in groups:
                        try:
                            group_folder = Path(root_dir) / str(g.get('name') or '')
                            if group_folder.exists() and group_folder.is_dir():
                                cnt = 0
                                for p in group_folder.rglob("*.*"):
                                    try:
                                        if p.is_file() and p.suffix.lower() in media_exts:
                                            cnt += 1
                                    except Exception:
                                        continue
                                new_cache[g.get('name')] = cnt
                            else:
                                new_cache[g.get('name')] = 0
                        except Exception:
                            new_cache[g.get('name')] = None
                    api_get_channel_groups._playlist_counts_cache = new_cache
                    api_get_channel_groups._playlist_counts_cache_ts = now
                    cache = new_cache
                # Apply cached values to response
                for g in groups:
                    g["playlist_tracks_count"] = cache.get(g.get('name'))
            except Exception:
                # Fallback to direct compute without cache if something goes wrong
                for g in groups:
                    try:
                        group_folder = Path(root_dir) / str(g.get('name') or '')
                        if group_folder.exists() and group_folder.is_dir():
                            cnt = 0
                            for p in group_folder.rglob("*.*"):
                                try:
                                    if p.is_file() and p.suffix.lower() in media_exts:
                                        cnt += 1
                                except Exception:
                                    continue
                            g["playlist_tracks_count"] = cnt
                        else:
                            g["playlist_tracks_count"] = 0
                    except Exception:
                        g["playlist_tracks_count"] = None
        
        log_message(f"[Channels] Retrieved {len(groups)} channel groups")
        return jsonify({"status": "ok", "groups": groups})
        
    except Exception as e:
        log_message(f"[Channels] Error retrieving channel groups: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_groups_bp.route("/groups/<int:group_id>")
def api_get_channels_by_group(group_id: int):
    """Get all channels in a specific group."""
    try:
        conn = get_connection()
        channels_raw = db.get_channels_by_group(conn, group_id)
        conn.close()
        
        # Convert sqlite3.Row objects to dictionaries
        channels = [dict(channel) for channel in channels_raw]
        
        log_message(f"[Channels] Retrieved {len(channels)} channels for group {group_id}")
        return jsonify({"status": "ok", "channels": channels})
        
    except Exception as e:
        log_message(f"[Channels] Error retrieving channels for group {group_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_groups_bp.route("/create_channel_group", methods=["POST"])
def api_create_channel_group():
    """Create a new channel group."""
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        behavior_type = data.get('behavior_type', 'music')
        auto_delete_enabled = data.get('auto_delete_enabled', False)
        include_in_likes = data.get('include_in_likes', True)
        play_order = data.get('play_order', 'random')
        
        # Validate required fields
        if not name:
            return jsonify({"status": "error", "error": "Group name is required"}), 400
        
        # Validate behavior type
        valid_behaviors = ['music', 'news', 'education', 'podcasts']
        if behavior_type not in valid_behaviors:
            return jsonify({"status": "error", "error": f"Invalid behavior type. Must be one of: {valid_behaviors}"}), 400
        
        # Validate play order
        valid_orders = ['random', 'newest_first', 'oldest_first']
        if play_order not in valid_orders:
            return jsonify({"status": "error", "error": f"Invalid play order. Must be one of: {valid_orders}"}), 400
        
        # Create group
        conn = get_connection()
        group_id = db.create_channel_group(
            conn, 
            name=name,
            behavior_type=behavior_type,
            auto_delete_enabled=auto_delete_enabled,
            include_in_likes=include_in_likes,
            play_order=play_order
        )
        conn.close()
        
        log_message(f"[Channels] Created channel group: {name} (ID: {group_id}, type: {behavior_type}, include_in_likes: {include_in_likes})")
        return jsonify({"status": "ok", "group_id": group_id, "message": f"Channel group '{name}' created successfully"})
        
    except Exception as e:
        log_message(f"[Channels] Error creating channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_groups_bp.route("/update_channel_group/<int:group_id>", methods=["POST"])
def api_update_channel_group(group_id: int):
    """Update channel group settings."""
    try:
        data = request.get_json() or {}
        
        # Get current group info
        conn = get_connection()
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Collect fields to update
        update_fields = {}
        
        # Update name if provided
        if 'name' in data:
            name = data.get('name', '').strip()
            if not name:
                conn.close()
                return jsonify({"status": "error", "error": "Group name cannot be empty"}), 400
            update_fields['name'] = name
        
        # Update behavior_type if provided
        if 'behavior_type' in data:
            behavior_type = data.get('behavior_type')
            valid_behaviors = ['music', 'news', 'education', 'podcasts']
            if behavior_type not in valid_behaviors:
                conn.close()
                return jsonify({"status": "error", "error": f"Invalid behavior type. Must be one of: {valid_behaviors}"}), 400
            update_fields['behavior_type'] = behavior_type
        
        # Update play_order if provided
        if 'play_order' in data:
            play_order = data.get('play_order')
            valid_orders = ['random', 'newest_first', 'oldest_first']
            if play_order not in valid_orders:
                conn.close()
                return jsonify({"status": "error", "error": f"Invalid play order. Must be one of: {valid_orders}"}), 400
            update_fields['play_order'] = play_order
        
        # Update auto_delete_enabled if provided
        if 'auto_delete_enabled' in data:
            update_fields['auto_delete_enabled'] = bool(data.get('auto_delete_enabled', False))
        
        # Update include_in_likes if provided
        if 'include_in_likes' in data:
            update_fields['include_in_likes'] = bool(data.get('include_in_likes', True))
        
        # Update folder_path if provided
        if 'folder_path' in data:
            update_fields['folder_path'] = data.get('folder_path')
        
        # Perform update
        if update_fields:
            updated = db.update_channel_group(conn, group_id, **update_fields)
            if updated:
                log_message(f"[Channels] Updated channel group {group_id}: {update_fields}")
                conn.close()
                return jsonify({"status": "ok", "message": f"Channel group updated successfully"})
            else:
                conn.close()
                return jsonify({"status": "error", "error": "Failed to update channel group"}), 500
        else:
            conn.close()
            return jsonify({"status": "error", "error": "No fields to update"}), 400
            
    except Exception as e:
        log_message(f"[Channels] Error updating channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_groups_bp.route("/delete_channel_group/<int:group_id>", methods=["POST"])
def api_delete_channel_group(group_id: int):
    """Delete an empty channel group."""
    try:
        conn = get_connection()
        
        # Get group info before deletion
        group = db.get_channel_group_by_id(conn, group_id)
        if not group:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        group_name = group['name']
        
        # Attempt to delete the group (will fail if it has channels)
        deleted = db.delete_channel_group(conn, group_id)
        conn.close()
        
        if deleted:
            log_message(f"[Channels] Deleted empty channel group: {group_name} (ID: {group_id})")
            return jsonify({
                "status": "success",
                "message": f"Empty channel group '{group_name}' deleted successfully"
            })
        else:
            return jsonify({
                "status": "error", 
                "error": "Cannot delete channel group - it still contains channels"
            }), 400
            
    except Exception as e:
        log_message(f"[Channels] Error deleting channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 