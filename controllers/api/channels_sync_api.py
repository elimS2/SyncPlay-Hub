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


@channels_sync_bp.route("/quick_sync_channel/<int:channel_id>", methods=["POST"])
def api_quick_sync_channel(channel_id: int):
    """Quick sync individual channel - creates a job in the queue for optimized processing."""
    try:
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
        
        # Create quick sync job in queue
        try:
            from services.job_queue_service import get_job_queue_service
            from services.job_types import JobType, JobPriority
            
            # Get job service
            job_service = get_job_queue_service()
            
            # Create quick sync job with high priority
            job_id = job_service.create_and_add_job(
                JobType.QUICK_SYNC,
                priority=JobPriority.HIGH,
                channel_id=channel_id,
                channel_name=channel['name'],
                channel_url=channel['url'],
                group_name=group['name'] if group else None
            )
            
            log_message(f"[Quick Sync API] Created quick sync job #{job_id} for channel '{channel['name']}'")
            
            return jsonify({
                "status": "started",
                "message": f"Quick sync job created for channel '{channel['name']}'. Job #{job_id} added to queue.",
                "job_id": job_id,
                "channel_name": channel['name'],
                "channel_id": channel_id,
                "process": "quick_sync_queued"
            })
            
        except ImportError:
            # Fallback if job queue not available
            log_message(f"[Quick Sync API] Job Queue System not available, falling back to immediate execution")
            
            # Use ChannelSyncService for immediate execution (fallback)
            sync_service = ChannelSyncService()
            result = sync_service.quick_sync_channel_core(channel_id=channel_id)
            
            # Log the operation
            if result.get('status') == 'started':
                log_message(f"[Quick Sync API] Started quick sync for channel '{channel['name']}' with {result.get('new_videos', 0)} new videos")
            elif result.get('status') == 'up_to_date':
                log_message(f"[Quick Sync API] Channel '{channel['name']}' is up to date")
            else:
                log_message(f"[Quick Sync API] Quick sync failed for channel '{channel['name']}': {result.get('error', 'Unknown error')}")
            
            return jsonify(result)
        
    except Exception as e:
        log_message(f"[Quick Sync API] Error creating quick sync job: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@channels_sync_bp.route("/quick_sync_channel_group/<int:group_id>", methods=["POST"])
def api_quick_sync_channel_group(group_id: int):
    """Quick sync all channels in a group - creates QUICK_SYNC jobs for all channels."""
    try:
        # Use ChannelSyncService for quick sync business logic
        sync_service = ChannelSyncService()
        
        # Execute quick sync for the entire group
        result = sync_service.quick_sync_channel_group(group_id=group_id)
        
        # Log the operation
        if result.get('status') == 'started':
            log_message(f"[Quick Sync Group API] Started quick sync for group '{result.get('group_name')}' with {result.get('jobs_created', 0)} jobs")
        else:
            log_message(f"[Quick Sync Group API] Quick sync group failed: {result.get('error', 'Unknown error')}")
        
        # Return result from service layer (already contains proper HTTP response format)
        return jsonify(result)
        
    except Exception as e:
        log_message(f"[Quick Sync Group API] Error quick syncing channel group: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500 