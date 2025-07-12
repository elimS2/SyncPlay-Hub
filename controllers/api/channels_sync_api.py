"""Channel Synchronization API endpoints."""

import re
import threading
import shutil
import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify

from .shared import get_connection, log_message, get_root_dir, record_event
import database as db
from services.channel_sync_service import ChannelSyncService

# Create blueprint
channels_sync_bp = Blueprint('channels_sync', __name__)

@channels_sync_bp.route("/sync_channel_group/<int:group_id>", methods=["POST"])
def api_sync_channel_group(group_id: int):
    """Sync all channels in a group using optimized Job Queue system (same as individual channel sync)."""
    try:
        data = request.get_json() or {}
        date_from = data.get('date_from')  # Optional date filter
        date_to = data.get('date_to')  # Optional date filter
        
        conn = get_connection()
        
        # Get group info
        group_raw = db.get_channel_group_by_id(conn, group_id)
        if not group_raw:
            conn.close()
            return jsonify({"status": "error", "error": "Channel group not found"}), 404
        
        # Convert to dict for easier access
        group = dict(group_raw)
        
        # Get channels in group
        channels_raw = db.get_channels_by_group(conn, group_id)
        if not channels_raw:
            conn.close()
            return jsonify({"status": "error", "error": "No channels found in group"}), 400
        
        # Convert sqlite3.Row objects to dictionaries
        channels = [dict(channel) for channel in channels_raw]
        
        conn.close()
        
        # Get ChannelSyncService instance
        sync_service = ChannelSyncService()
        
        # Start background sync for all channels using ChannelSyncService
        def _sync_worker():
            try:
                success_count = 0
                failed_count = 0
                
                for channel in channels:
                    try:
                        # Use ChannelSyncService instead of internal sync_single_channel
                        result = sync_service.sync_single_channel_core(
                            channel_id=channel['id'],
                            date_from=date_from,
                            date_to=date_to
                        )
                        
                        # Check if sync was successful based on result status
                        if result.get('status') == 'started':
                            success_count += 1
                        else:
                            failed_count += 1
                            log_message(f"[Group Sync] Channel {channel['name']} sync failed: {result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        failed_count += 1
                        log_message(f"[Group Sync] Error syncing channel {channel['name']}: {e}")
                
                log_message(f"[Group Sync] Completed group '{group['name']}': {success_count} channels started, {failed_count} failed")
                
            except Exception as e:
                log_message(f"[Group Sync] Error syncing group '{group['name']}': {e}")
        
        # Start sync in background
        sync_thread = threading.Thread(target=_sync_worker, daemon=True)
        sync_thread.start()
        
        log_message(f"[Channels] Started optimized sync for group '{group['name']}' with {len(channels)} channels")
        
        return jsonify({
            "status": "started", 
            "message": f"Optimized sync started for {len(channels)} channels in group '{group['name']}'",
            "group_name": group['name'],
            "channels_count": len(channels),
            "date_filter": {"from": date_from, "to": date_to} if date_from or date_to else None,
            "sync_type": "optimized_job_queue"
        })
        
    except Exception as e:
        log_message(f"[Channels] Error syncing channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@channels_sync_bp.route("/sync_channel/<int:channel_id>", methods=["POST"])
def api_sync_channel(channel_id: int):
    """Sync individual channel using Job Queue system (same logic as channel addition)."""
    try:
        data = request.get_json() or {}
        date_from = data.get('date_from')  # Optional date filter
        date_to = data.get('date_to')  # Optional date filter
        
        conn = get_connection()
        
        # Get channel info
        channel_raw = db.get_channel_by_id(conn, channel_id)
        if not channel_raw:
            conn.close()
            return jsonify({"status": "error", "error": "Channel not found"}), 404
        
        # Convert to dict for easier access
        channel = dict(channel_raw)
        
        # Get group info
        group_raw = db.get_channel_group_by_id(conn, channel['channel_group_id'])
        group = dict(group_raw) if group_raw else None
        
        conn.close()
        
        # Use ChannelSyncService for channel sync business logic
        sync_service = ChannelSyncService()
        
        # Execute channel sync using service layer
        result = sync_service.sync_single_channel_core(
            channel_id=channel_id,
            date_from=date_from,
            date_to=date_to
        )
        
        # Return result from service layer (already contains proper HTTP response format)
        return jsonify(result)
        
    except Exception as e:
        log_message(f"[Channels] Error syncing channel: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 