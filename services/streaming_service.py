"""Streaming service for shared viewing functionality."""

import time
import uuid
import threading
import queue
from typing import Dict, List

# Global streams storage - matching original web_player.py structure
# In-memory store: {stream_id: {"state":{...}, "clients":set(), "title":str, "created":ts}}
STREAMS: dict[str, dict] = {}
_streams_lock = threading.Lock()

def _prune_streams():
    """Remove streams with no clients for >30 min."""
    now = time.time()
    with _streams_lock:
        stale = [sid for sid, s in STREAMS.items() if not s["clients"] and now - s["created"] > 1800]
        for sid in stale:
            STREAMS.pop(sid, None)

def get_streams() -> List[Dict]:
    """Get list of active streams."""
    _prune_streams()
    with _streams_lock:
        items = [
            {
                "id": sid,
                "title": s.get("title", "Stream"),
                "listeners": len(s["clients"]),
            }
            for sid, s in STREAMS.items()
        ]
    return items

def create_stream(title: str, queue_data: List = None, idx: int = 0, position: int = 0) -> str:
    """Create a new stream and return its ID."""
    stream_id = uuid.uuid4().hex[:8]
    with _streams_lock:
        STREAMS[stream_id] = {
            "state": {
                "queue": queue_data or [],
                "idx": idx,
                "position": position,
                "paused": True,
            },
            "clients": set(),
            "title": title,
            "created": time.time(),
        }
    return stream_id

def get_stream(stream_id: str) -> Dict:
    """Get stream data by ID."""
    with _streams_lock:
        return STREAMS.get(stream_id)

def update_stream_state(stream_id: str, event_data: Dict):
    """Update stream state and notify clients."""
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if not s:
            return False
        
        # Update state
        action = event_data.get("action")
        if action in {"play", "pause", "seek", "next", "prev"}:
            # Generic update of known fields
            for key in ("idx", "position", "paused"):
                if key in event_data:
                    s["state"][key] = event_data[key]
            s["state"]["last_action"] = action
        
        # Fan-out to clients
        for q in list(s["clients"]):
            try:
                q.put(event_data, timeout=0.1)
            except Exception:
                pass
        
        return True

def add_stream_client(stream_id: str) -> queue.Queue:
    """Add a client to stream and return their queue."""
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if not s:
            return None
        
        q = queue.Queue()
        s["clients"].add(q)
        return q

def remove_stream_client(stream_id: str, client_queue):
    """Remove a client from stream notifications."""
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if s:
            s["clients"].discard(client_queue)

def get_stream_state(stream_id: str) -> Dict:
    """Get current stream state."""
    with _streams_lock:
        s = STREAMS.get(stream_id)
        if s:
            return s["state"].copy()
        return {} 