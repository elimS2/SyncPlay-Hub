"""File browser API endpoints."""

from pathlib import Path
from flask import Blueprint, jsonify, send_from_directory
from .shared import get_root_dir, log_message, _format_file_size

# Create blueprint
browser_bp = Blueprint('browser', __name__)

@browser_bp.route("/browse", defaults={"subpath": ""})
@browser_bp.route("/browse/<path:subpath>")
def api_browse(subpath: str):
    """Browse directory structure and files."""
    try:
        # Start from ROOT_DIR parent to show the full data structure
        root_dir = get_root_dir()
        base_dir = root_dir.parent if root_dir else Path.cwd()
        
        # Handle subpath safely
        if subpath:
            target_dir = base_dir / subpath
            # Security check: ensure path is within base_dir
            target_dir = target_dir.resolve()
            if base_dir not in target_dir.parents and target_dir != base_dir:
                return jsonify({"error": "Invalid path"}), 400
        else:
            target_dir = base_dir
        
        if not target_dir.exists() or not target_dir.is_dir():
            return jsonify({"error": "Directory not found"}), 404
        
        items = []
        try:
            for item in sorted(target_dir.iterdir()):
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                    
                item_data = {
                    "name": item.name,
                    "path": str(item.relative_to(base_dir)).replace("\\", "/"),
                    "is_dir": item.is_dir()
                }
                
                if item.is_file():
                    try:
                        stat = item.stat()
                        item_data.update({
                            "size": stat.st_size,
                            "size_human": _format_file_size(stat.st_size),
                            "modified": stat.st_mtime,
                            "is_media": item.suffix.lower() in {".mp3", ".m4a", ".opus", ".webm", ".flac", ".mp4", ".mkv", ".mov"}
                        })
                    except OSError:
                        item_data.update({
                            "size": 0,  
                            "size_human": "0 B",
                            "modified": 0,
                            "is_media": False
                        })
                
                items.append(item_data)
        except PermissionError:
            return jsonify({"error": "Permission denied"}), 403
        
        # Add parent navigation (if not at root)
        parent_path = ""
        if target_dir != base_dir:
            parent_rel = target_dir.parent.relative_to(base_dir)
            parent_path = str(parent_rel).replace("\\", "/") if str(parent_rel) != "." else ""
        
        return jsonify({
            "current_path": str(target_dir.relative_to(base_dir)).replace("\\", "/") if target_dir != base_dir else "",
            "parent_path": parent_path,
            "can_go_up": target_dir != base_dir,
            "items": items
        })
        
    except Exception as exc:
        log_message(f"[Browse] Error: {exc}")
        return jsonify({"error": str(exc)}), 500

@browser_bp.route("/download_file/<path:filepath>")
def api_download_file(filepath: str):
    """Download a file from the data directory."""
    try:
        root_dir = get_root_dir() 
        base_dir = root_dir.parent if root_dir else Path.cwd()
        file_path = base_dir / filepath
        
        # Security check
        file_path = file_path.resolve()
        if base_dir not in file_path.parents and file_path != base_dir:
            return jsonify({"error": "Invalid path"}), 400
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "File not found"}), 404
        
        return send_from_directory(base_dir, filepath, as_attachment=True)
        
    except Exception as exc:
        log_message(f"[DownloadFile] Error: {exc}")
        return jsonify({"error": str(exc)}), 500 