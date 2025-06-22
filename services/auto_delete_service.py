"""Auto-Delete Service for Channel Content Management

This service automatically deletes tracks after they finish playing,
but only for channels with auto-delete enabled and with multiple safety checks.

Safety Rules:
1. Track must have finished playing (not skipped)
2. Play duration must be ≥5 seconds
3. Track must not be liked
4. No 'next' events after 'finish' event
5. Channel group must have auto_delete_enabled=True
6. Must be from a channel (not playlist)
"""

import sqlite3
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from utils.logging_utils import log_message


class AutoDeleteService:
    def __init__(self):
        self.is_running = False
        self.check_interval = 30  # Check every 30 seconds
        self.worker_thread = None
        self.root_dir = None
        
    def start(self, root_dir: Path):
        """Start the auto-delete service."""
        if self.is_running:
            log_message("[AutoDelete] Service already running")
            return
            
        self.root_dir = root_dir
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        log_message("[AutoDelete] Service started")
        
    def stop(self):
        """Stop the auto-delete service."""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        log_message("[AutoDelete] Service stopped")
        
    def _worker_loop(self):
        """Main worker loop that periodically checks for tracks to delete."""
        while self.is_running:
            try:
                self._check_for_deletions()
            except Exception as e:
                log_message(f"[AutoDelete] Error in worker loop: {e}")
            
            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.check_interval):
                if not self.is_running:
                    break
                time.sleep(1)
                
    def _check_for_deletions(self):
        """Check for tracks that should be auto-deleted."""
        try:
            from database import get_connection
            
            conn = get_connection()
            
            # Find tracks that finished playing recently and might need deletion
            # Look for tracks that:
            # 1. Have a recent 'finish' event (within last 5 minutes)
            # 2. Are from channels with auto-delete enabled
            # 3. Haven't been processed for auto-delete yet
            
            query = """
            SELECT DISTINCT 
                t.id, t.video_id, t.relpath, t.channel_group,
                ph.ts, ph.position, ph.id as event_id
            FROM tracks t
            JOIN play_history ph ON t.video_id = ph.video_id
            LEFT JOIN channel_groups cg ON t.channel_group = cg.name
            WHERE ph.event = 'finish'
                AND ph.ts >= datetime('now', '-5 minutes')
                AND t.auto_delete_after_finish = 1
                AND cg.auto_delete_enabled = 1
                AND t.channel_group IS NOT NULL
                AND t.relpath LIKE '%Channel-%'
            ORDER BY ph.ts DESC
            """
            
            cursor = conn.cursor()
            cursor.execute(query)
            candidates = cursor.fetchall()
            
            for candidate in candidates:
                track_id = candidate[0]
                video_id = candidate[1]
                relpath = candidate[2]
                channel_group = candidate[3]
                finish_ts = candidate[4]
                finish_position = candidate[5]
                finish_event_id = candidate[6]
                
                # Check if this track should be auto-deleted
                if self._should_auto_delete(conn, video_id, finish_event_id, finish_position):
                    success = self._auto_delete_track(conn, track_id, video_id, relpath, channel_group, finish_ts)
                    if success:
                        log_message(f"[AutoDelete] Successfully deleted track: {video_id} from {channel_group}")
                    else:
                        log_message(f"[AutoDelete] Failed to delete track: {video_id}")
            
            conn.close()
            
        except Exception as e:
            log_message(f"[AutoDelete] Error checking for deletions: {e}")
            
    def _should_auto_delete(self, conn: sqlite3.Connection, video_id: str, 
                           finish_event_id: int, finish_position: float) -> bool:
        """
        Check if a track should be auto-deleted based on safety rules.
        
        Safety Rules:
        1. Play duration ≥5 seconds
        2. Not liked
        3. No 'next' events after the finish event
        4. No recent play events (track actually finished, not paused)
        """
        try:
            cursor = conn.cursor()
            
            # Rule 1: Check play duration (≥5 seconds)
            if finish_position < 5.0:
                log_message(f"[AutoDelete] Skipping {video_id}: play duration {finish_position:.1f}s < 5s")
                return False
            
            # Rule 2: Check if track is liked
            cursor.execute("""
                SELECT COUNT(*) FROM play_history 
                WHERE video_id = ? AND event = 'like'
            """, (video_id,))
            
            if cursor.fetchone()[0] > 0:
                log_message(f"[AutoDelete] Skipping {video_id}: track is liked")
                return False
            
            # Rule 3: Check for 'next' events after the finish event
            cursor.execute("""
                SELECT COUNT(*) FROM play_history 
                WHERE video_id = ? AND event = 'next' AND id > ?
            """, (video_id, finish_event_id))
            
            if cursor.fetchone()[0] > 0:
                log_message(f"[AutoDelete] Skipping {video_id}: has 'next' events after finish")
                return False
            
            # Rule 4: Check for recent play events (within 1 minute after finish)
            cursor.execute("""
                SELECT COUNT(*) FROM play_history 
                WHERE video_id = ? 
                    AND event IN ('play', 'start') 
                    AND id > ?
                    AND ts >= datetime('now', '-1 minute')
            """, (video_id, finish_event_id))
            
            if cursor.fetchone()[0] > 0:
                log_message(f"[AutoDelete] Skipping {video_id}: has recent play events after finish")
                return False
            
            log_message(f"[AutoDelete] Track {video_id} passed all safety checks, eligible for deletion")
            return True
            
        except Exception as e:
            log_message(f"[AutoDelete] Error checking safety rules for {video_id}: {e}")
            return False
            
    def _auto_delete_track(self, conn: sqlite3.Connection, track_id: int, video_id: str, 
                          relpath: str, channel_group: str, finish_ts: str) -> bool:
        """
        Auto-delete a track by moving it to trash and recording the deletion.
        """
        try:
            if not self.root_dir or not relpath:
                log_message(f"[AutoDelete] Cannot delete {video_id}: missing root_dir or relpath")
                return False
                
            # Construct full file path
            full_file_path = self.root_dir / relpath
            
            if not full_file_path.exists():
                log_message(f"[AutoDelete] File not found for deletion: {full_file_path}")
                return False
            
            # Move file to trash
            from download_content import move_to_trash
            moved_to_trash = move_to_trash(full_file_path, self.root_dir)
            
            if not moved_to_trash:
                log_message(f"[AutoDelete] Failed to move {video_id} to trash")
                return False
            
            # Record deletion in database
            cursor = conn.cursor()
            
            # Add to deleted_tracks table
            cursor.execute("""
                INSERT INTO deleted_tracks (
                    video_id, original_path, channel_group, 
                    deletion_reason, deleted_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                video_id, 
                file_path, 
                channel_group,
                'auto_delete_after_finish',
                finish_time
            ))
            
            # Record deletion event in play_history
            cursor.execute("""
                INSERT INTO play_history (video_id, event, event_time, position, extra_data)
                VALUES (?, 'auto_deleted', datetime('now'), ?, ?)
            """, (video_id, 0.0, f'channel_group:{channel_group}'))
            
            # Update track record (mark as deleted)
            cursor.execute("""
                UPDATE tracks SET 
                    file_path = NULL,
                    deleted_at = datetime('now'),
                    deletion_reason = 'auto_delete_after_finish'
                WHERE id = ?
            """, (track_id,))
            
            conn.commit()
            
            log_message(f"[AutoDelete] Successfully processed deletion for {video_id} from {channel_group}")
            return True
            
        except Exception as e:
            log_message(f"[AutoDelete] Error deleting track {video_id}: {e}")
            try:
                conn.rollback()
            except:
                pass
            return False


# Global service instance
_auto_delete_service = None

def get_auto_delete_service() -> AutoDeleteService:
    """Get the global auto-delete service instance."""
    global _auto_delete_service
    if _auto_delete_service is None:
        _auto_delete_service = AutoDeleteService()
    return _auto_delete_service

def start_auto_delete_service(root_dir: Path):
    """Start the auto-delete service."""
    service = get_auto_delete_service()
    service.start(root_dir)

def stop_auto_delete_service():
    """Stop the auto-delete service."""
    service = get_auto_delete_service()
    service.stop()

def trigger_auto_delete_check(video_id: str, finish_position: float):
    """
    Trigger an immediate auto-delete check for a specific track.
    This is called when a track finishes playing.
    """
    try:
        service = get_auto_delete_service()
        if not service.is_running:
            return
            
        # This will be handled by the periodic check, but we could add
        # immediate processing here if needed
        log_message(f"[AutoDelete] Finish event received for {video_id} at position {finish_position:.1f}s")
        
    except Exception as e:
        log_message(f"[AutoDelete] Error in trigger_auto_delete_check: {e}") 