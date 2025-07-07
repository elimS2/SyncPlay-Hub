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
            play_order=play_order
        )
        conn.close()
        
        log_message(f"[Channels] Created channel group: {name} (ID: {group_id}, type: {behavior_type})")
        return jsonify({"status": "ok", "group_id": group_id, "message": f"Channel group '{name}' created successfully"})
        
    except Exception as e:
        log_message(f"[Channels] Error creating channel group: {e}")
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