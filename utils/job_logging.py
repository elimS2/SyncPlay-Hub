#!/usr/bin/env python3
"""
Job Logging System

Individual logging system for Job Queue tasks.
Each task gets a separate folder with logs.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, TextIO
from datetime import datetime
from contextlib import contextmanager
import threading
from io import StringIO


class JobLogger:
    """Logger for individual task with capture of all outputs."""
    
    def __init__(self, job_id: int, job_type: str, logs_root: str = None):
        self.job_id = job_id
        self.job_type = job_type
        
        # Determine root logs folder
        if logs_root is None:
            # Use same structure as main logs
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            env_path = project_root / '.env'
            
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip().lstrip('\ufeff')
                            if line.startswith('LOG_DIR='):
                                logs_root = line.split('=', 1)[1].strip()
                                break
                except Exception:
                    pass
            
            if not logs_root:
                logs_root = str(project_root / 'logs')
        
        # Create folder for task
        self.job_log_dir = Path(logs_root) / 'jobs' / f"job_{job_id:06d}_{job_type}"
        self.job_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Log files
        self.main_log_file = self.job_log_dir / 'job.log'
        self.stdout_file = self.job_log_dir / 'stdout.log'
        self.stderr_file = self.job_log_dir / 'stderr.log'
        self.progress_file = self.job_log_dir / 'progress.log'
        
        # Setup logger
        self.logger = logging.getLogger(f'job_{job_id}')
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create handler for main log
        main_handler = logging.FileHandler(self.main_log_file, encoding='utf-8')
        main_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        main_handler.setFormatter(formatter)
        self.logger.addHandler(main_handler)
        
        # Capture stdout/stderr
        self._original_stdout = None
        self._original_stderr = None
        self._stdout_capture = None
        self._stderr_capture = None
        
        # Thread-local storage for multiple tasks
        self._local = threading.local()
        
        # Write task start
        self.info(f"=== Job {job_id} ({job_type}) started at {datetime.utcnow().isoformat()} ===")
    
    def info(self, message: str):
        """Log informational message."""
        self.logger.info(message)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    def progress(self, message: str, percentage: Optional[float] = None):
        """Log execution progress."""
        timestamp = datetime.utcnow().isoformat()
        
        if percentage is not None:
            progress_msg = f"[{percentage:6.2f}%] {message}"
        else:
            progress_msg = message
        
        # Write to main log
        self.info(f"PROGRESS: {progress_msg}")
        
        # Write to progress file
        with open(self.progress_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} {progress_msg}\n")
    
    def log_exception(self, exc: Exception, context: str = ""):
        """Log exception with context."""
        import traceback
        
        error_msg = f"Exception in {context}: {type(exc).__name__}: {exc}"
        self.error(error_msg)
        
        # Write full traceback
        tb_str = traceback.format_exc()
        self.error(f"Traceback:\n{tb_str}")
    
    @contextmanager
    def capture_output(self):
        """Context manager for capturing stdout/stderr."""
        # Save original streams
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Create files for capture
            stdout_file = open(self.stdout_file, 'a', encoding='utf-8')
            stderr_file = open(self.stderr_file, 'a', encoding='utf-8')
            
            # Create tee-like objects for duplicating output
            sys.stdout = TeeOutput(original_stdout, stdout_file)
            sys.stderr = TeeOutput(original_stderr, stderr_file)
            
            yield
            
        finally:
            # Restore original streams
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Close files
            if stdout_file:
                stdout_file.close()
            if stderr_file:
                stderr_file.close()
    
    def finalize(self, success: bool, error_message: Optional[str] = None):
        """Finalize task logging."""
        status = "COMPLETED" if success else "FAILED"
        end_time = datetime.utcnow().isoformat()
        
        self.info(f"=== Job {self.job_id} {status} at {end_time} ===")
        
        if error_message:
            self.error(f"Final error: {error_message}")
        
        # Write summary file
        summary_file = self.job_log_dir / 'summary.txt'
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"Job ID: {self.job_id}\n")
            f.write(f"Job Type: {self.job_type}\n")
            f.write(f"Status: {status}\n")
            f.write(f"End Time: {end_time}\n")
            if error_message:
                f.write(f"Error: {error_message}\n")
            f.write(f"\nLog Files:\n")
            f.write(f"- Main Log: {self.main_log_file.name}\n")
            f.write(f"- Stdout: {self.stdout_file.name}\n")
            f.write(f"- Stderr: {self.stderr_file.name}\n")
            f.write(f"- Progress: {self.progress_file.name}\n")
        
        # Close handlers
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()
    
    def get_log_files(self) -> dict:
        """Returns paths to all log files."""
        return {
            'main': str(self.main_log_file),
            'stdout': str(self.stdout_file),
            'stderr': str(self.stderr_file),
            'progress': str(self.progress_file),
            'summary': str(self.job_log_dir / 'summary.txt'),
            'directory': str(self.job_log_dir)
        }


class TeeOutput:
    """Class for duplicating output to multiple streams."""
    
    def __init__(self, *outputs):
        self.outputs = outputs
    
    def write(self, data):
        for output in self.outputs:
            try:
                output.write(data)
                output.flush()
            except Exception:
                pass  # Ignore write errors
    
    def flush(self):
        for output in self.outputs:
            try:
                output.flush()
            except Exception:
                pass


def create_job_logger(job_id: int, job_type: str, logs_root: str = None) -> JobLogger:
    """Factory function for creating task logger."""
    return JobLogger(job_id, job_type, logs_root)


def cleanup_old_job_logs(logs_root: str = None, days_to_keep: int = 30):
    """Cleanup old task logs."""
    if logs_root is None:
        # Use same code as in JobLogger for determining logs_root
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        env_path = project_root / '.env'
        
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip().lstrip('\ufeff')
                        if line.startswith('LOG_DIR='):
                            logs_root = line.split('=', 1)[1].strip()
                            break
            except Exception:
                pass
        
        if not logs_root:
            logs_root = str(project_root / 'logs')
    
    jobs_dir = Path(logs_root) / 'jobs'
    if not jobs_dir.exists():
        return
    
    cutoff_time = datetime.utcnow().timestamp() - (days_to_keep * 24 * 3600)
    
    cleaned_count = 0
    for job_dir in jobs_dir.iterdir():
        if job_dir.is_dir() and job_dir.name.startswith('job_'):
            # Check last modification time
            if job_dir.stat().st_mtime < cutoff_time:
                try:
                    import shutil
                    shutil.rmtree(job_dir)
                    cleaned_count += 1
                except Exception as e:
                    print(f"Failed to remove old job log directory {job_dir}: {e}")
    
    if cleaned_count > 0:
        print(f"Cleaned up {cleaned_count} old job log directories") 