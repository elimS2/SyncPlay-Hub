"""System control API endpoints."""

import subprocess
import sys
import os
import datetime
import threading
import time
import signal
from pathlib import Path
from flask import Blueprint, request, jsonify
from .shared import log_message

# Create blueprint
system_bp = Blueprint('system', __name__)

@system_bp.route("/restart", methods=["POST"])
def api_restart():
    """Restart Flask server using self-restart mechanism."""
    
    def restart_server():
        # Give a moment for the response to be sent
        time.sleep(0.5)
        
        # Log current PID before restart
        current_pid = os.getpid()
        log_message(f"Initiating restart of server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Build restart command with same arguments + --force to bypass duplicate check
        restart_cmd = [sys.executable] + sys.argv + ["--force"]
        
        try:
            # Start new process in same console window (no CREATE_NEW_CONSOLE)
            if os.name == 'nt':  # Windows
                # Use subprocess without creating new console window
                subprocess.Popen(restart_cmd, creationflags=0)
            else:  # Unix/Linux/Mac
                subprocess.Popen(restart_cmd)
            
            log_message(f"New server process started, terminating current PID {current_pid}")
            
            # Clean up PID file before exit to allow new process to start
            try:
                pid_file = Path.cwd() / "syncplay_hub.pid"
                pid_file.unlink(missing_ok=True)
                log_message("PID file cleaned up for restart")
            except Exception as e:
                log_message(f"Warning: Could not clean PID file: {e}")
            
            # Give new process time to start before terminating
            time.sleep(1.5)
            os._exit(0)  # Force exit current process
            
        except Exception as e:
            log_message(f"Error during restart: {e}")
    
    # Start restart in a separate thread
    threading.Thread(target=restart_server, daemon=True).start()
    
    return jsonify({"status": "ok", "message": "Server restarting..."})

@system_bp.route("/stop", methods=["POST"])
def api_stop():
    """Stop Flask server gracefully."""
    
    def stop_server():
        # Give a moment for the response to be sent
        time.sleep(0.5)
        
        # Log current PID before stopping
        current_pid = os.getpid()
        log_message(f"Stopping server PID {current_pid} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Clean up PID file before exit
        try:
            pid_file = Path.cwd() / "syncplay_hub.pid"
            pid_file.unlink(missing_ok=True)
            log_message("PID file cleaned up")
        except Exception as e:
            log_message(f"Warning: Could not clean PID file: {e}")
        
        log_message("Server stopped gracefully")
        log_message("You can restart the server by running the same command again")
        
        # Graceful shutdown using Flask's built-in mechanism
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            # Fallback for different WSGI servers
            os.kill(os.getpid(), signal.SIGTERM)
        else:
            func()
    
    # Start stop in a separate thread
    threading.Thread(target=stop_server, daemon=True).start()
    
    return jsonify({"status": "ok", "message": "Server stopping..."}) 