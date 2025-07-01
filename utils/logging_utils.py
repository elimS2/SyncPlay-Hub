"""Centralized logging utilities for the application."""

import os
import sys
import datetime
import logging
import threading
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Global variables for logging
LOGS_DIR = None
SERVER_PID = None
SERVER_START_TIME = None
_downloads_lock = threading.Lock()

def set_logs_dir(logs_dir: Path):
    """Set the global LOGS_DIR variable."""
    global LOGS_DIR
    LOGS_DIR = logs_dir

def init_logging(logs_dir: Path, pid: int, start_time: datetime.datetime):
    """Initialize the logging system."""
    global LOGS_DIR, SERVER_PID, SERVER_START_TIME
    LOGS_DIR = logs_dir
    SERVER_PID = pid
    SERVER_START_TIME = start_time
    
    # Ensure logs directory exists
    logs_dir.mkdir(parents=True, exist_ok=True)

class NoSyncInternalFilter(logging.Filter):
    """Filter to remove noisy remote control HTTP requests from logs."""
    
    def filter(self, record):
        # Filter out frequent polling requests as they are too noisy and not important
        # Only filter successful (200) requests - keep errors visible for debugging
        message = record.getMessage()
        # Remote control requests
        if 'POST /api/remote/sync_internal HTTP/1.1" 200 -' in message:
            return False
        if 'GET /api/remote/commands HTTP/1.1" 200 -' in message:
            return False
        if 'GET /api/remote/status HTTP/1.1" 200 -' in message:
            return False
        # Jobs API polling requests
        if 'GET /api/jobs/queue/status HTTP/1.1" 200 -' in message:
            return False
        if 'GET /api/jobs HTTP/1.1" 200 -' in message:
            return False
        if 'GET /api/jobs?' in message and 'HTTP/1.1" 200 -' in message:
            return False
        return True

class AnsiCleaningStream:
    """Stream wrapper that removes ANSI codes before writing to file."""
    
    def __init__(self, original_stream, file_handler):
        self.original_stream = original_stream
        self.file_handler = file_handler

    def write(self, text):
        # Write original (with colors) to console
        self.original_stream.write(text)
        # DON'T write to file here - DualStreamHandler already does it!

    def flush(self):
        self.original_stream.flush()

    def _remove_ansi_codes(self, text):
        """Remove ANSI escape sequences from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def __getattr__(self, name):
        # Delegate other attributes to original stream
        return getattr(self.original_stream, name)

class DualStreamHandler(logging.Handler):
    """Custom logging handler that writes to both console and file."""
    
    def __init__(self, file_handler):
        super().__init__()
        self.file_handler = file_handler

    def emit(self, record):
        try:
            # Get original message and clean it (like original)
            original_msg = record.getMessage()
            clean_msg = self._remove_ansi_codes(original_msg)
            
            # Remove Flask's timestamp from HTTP logs for cleaner output
            clean_msg = self._remove_flask_timestamp(clean_msg)
            
            # For console: use cleaned message (log_message will add timestamp+PID)
            # Safely handle encoding for Windows console
            try:
                print(clean_msg, flush=True)
            except UnicodeEncodeError:
                # Handle Windows console encoding issues
                safe_msg = clean_msg.encode('ascii', 'replace').decode('ascii')
                print(safe_msg, flush=True)
            
            # Create a copy of the record with cleaned message for file handler
            file_record = logging.LogRecord(
                record.name, record.levelno, record.pathname, record.lineno,
                clean_msg, (), record.exc_info, record.funcName, record.stack_info
            )
            file_record.created = record.created
            file_record.msecs = record.msecs
            file_record.relativeCreated = record.relativeCreated
            file_record.thread = record.thread
            file_record.threadName = record.threadName
            file_record.processName = record.processName
            file_record.process = record.process
            
            # Write to file (file_handler will add its own timestamp+PID formatting)
            self.file_handler.emit(file_record)
            
        except Exception:
            self.handleError(record)

    def _remove_flask_timestamp(self, message):
        """Remove Flask's built-in timestamp from HTTP log messages"""
        if ' - - [' in message and '] "' in message:
            # Extract just the IP and request part, skip the timestamp
            parts = message.split(' - - [', 1)
            if len(parts) == 2:
                ip_part = parts[0]
                rest_parts = parts[1].split('] ', 1)
                if len(rest_parts) == 2:
                    request_part = rest_parts[1]
                    return f"{ip_part} - - {request_part}"
        return message

    def _remove_ansi_codes(self, text):
        """Remove ANSI escape sequences from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

# Global unified logger
unified_logger = None

def log_message(message):
    """Log function that writes simultaneously to both console and file"""
    if unified_logger:
        unified_logger.info(message)
    else:
        # Fallback if logger not initialized - safely handle encoding
        try:
            print(message, flush=True)
        except UnicodeEncodeError:
            # Handle Windows console encoding issues
            safe_message = message.encode('ascii', 'replace').decode('ascii')
            print(safe_message, flush=True)

def setup_logging():
    """Set up the unified logging system like original."""
    global unified_logger
    if not LOGS_DIR:
        return
        
    # Create main log file handler
    main_log_file = LOGS_DIR / "SyncPlay-Hub.log"
    file_handler = RotatingFileHandler(
        main_log_file, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [PID %(process)d] %(message)s', '%Y-%m-%d %H:%M:%S'))
    
    # Create our unified logger with dual stream handler
    unified_logger = logging.getLogger('syncplay_unified')
    unified_logger.setLevel(logging.INFO)
    unified_logger.propagate = False
    
    # Add dual stream handler that writes to both console and file
    dual_handler = DualStreamHandler(file_handler)
    dual_handler.setFormatter(logging.Formatter('%(message)s'))  # Simple format since timestamp is added by file_handler
    unified_logger.addHandler(dual_handler)
    
    # Create filter to remove noisy sync_internal requests
    sync_filter = NoSyncInternalFilter()
    
    # Configure Flask's werkzeug logger to use our unified system
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers.clear()  # Remove default handlers
    werkzeug_logger.addHandler(dual_handler)
    werkzeug_logger.addFilter(sync_filter)  # Add filter to remove sync_internal logs
    werkzeug_logger.propagate = False
    
    # Intercept stdout/stderr to catch any direct prints from Flask
    sys.stdout = AnsiCleaningStream(sys.__stdout__, file_handler)
    sys.stderr = AnsiCleaningStream(sys.__stderr__, file_handler) 