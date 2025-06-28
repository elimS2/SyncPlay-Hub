"""Streaming API endpoints."""

import json
from flask import Blueprint, request, jsonify, Response, url_for
from services.streaming_service import (
    get_streams, create_stream, get_stream, update_stream_state, 
    add_stream_client, remove_stream_client, get_stream_state
)

# Create blueprint
streaming_bp = Blueprint('streaming', __name__)

@streaming_bp.route("/streams")
def api_streams():
    """Get list of active streams."""
    return jsonify(get_streams())

@streaming_bp.route("/create_stream", methods=["POST"])
def api_create_stream():
    """Create a new stream."""
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title") or "Untitled Stream"
    
    stream_id = create_stream(
        title=title,
        queue_data=data.get("queue", []),
        idx=data.get("idx", 0),
        position=data.get("position", 0)
    )
    
    return jsonify({
        "id": stream_id,
        "url": url_for("stream_page", stream_id=stream_id, _external=True)
    })

@streaming_bp.route("/stream_event/<stream_id>", methods=["POST"])
def api_stream_event(stream_id: str):
    """Update stream state."""
    evt = request.get_json(force=True, silent=True) or {}
    
    success = update_stream_state(stream_id, evt)
    if not success:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    return jsonify({"status": "ok"})

@streaming_bp.route("/stream_feed/<stream_id>")
def api_stream_feed(stream_id: str):
    """Server-sent events feed for stream."""
    stream = get_stream(stream_id)
    if not stream:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    client_queue = add_stream_client(stream_id)
    if not client_queue:
        return jsonify({"status": "error", "message": "stream not found"}), 404
    
    def gen():
        try:
            # Send initial state
            init_payload = json.dumps({"init": get_stream_state(stream_id)})
            yield f"data: {init_payload}\n\n"
            
            # Listen for new events
            while True:
                msg = client_queue.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except GeneratorExit:
            pass
        finally:
            remove_stream_client(stream_id, client_queue)
    
    return Response(gen(), mimetype="text/event-stream") 