#!/usr/bin/env python3
"""
Migration 001: Create job_queue table

Creates table for managing job queue with full support for
logging, priorities and execution status tracking.
"""

from database.migration_manager import Migration
import sqlite3


class Migration001(Migration):
    """Create job_queue table for job queue system."""
    
    def up(self, conn: sqlite3.Connection) -> None:
        """Creates job_queue table and related indexes."""
        
        # Main table for job queue
        conn.execute('''
            CREATE TABLE job_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                job_data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' 
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                priority INTEGER NOT NULL DEFAULT 0,
                
                created_at TEXT DEFAULT (datetime('now', 'utc')),
                started_at TEXT NULL,
                completed_at TEXT NULL,
                
                log_file_path TEXT NULL,
                error_message TEXT NULL,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                
                worker_id TEXT NULL,
                timeout_seconds INTEGER NULL,
                
                parent_job_id INTEGER NULL,
                
                FOREIGN KEY (parent_job_id) REFERENCES job_queue(id)
            )
        ''')
        
        # Indexes for performance
        conn.execute('CREATE INDEX idx_job_queue_status ON job_queue(status)')
        conn.execute('CREATE INDEX idx_job_queue_type ON job_queue(job_type)')
        conn.execute('CREATE INDEX idx_job_queue_priority ON job_queue(priority DESC)')
        conn.execute('CREATE INDEX idx_job_queue_created_at ON job_queue(created_at)')
        conn.execute('CREATE INDEX idx_job_queue_status_priority ON job_queue(status, priority DESC)')
        
        print("✅ Created job_queue table with all indexes")
    
    def down(self, conn: sqlite3.Connection) -> None:
        """Deletes job_queue table and related indexes."""
        
        # First delete indexes
        conn.execute('DROP INDEX IF EXISTS idx_job_queue_status_priority')
        conn.execute('DROP INDEX IF EXISTS idx_job_queue_created_at')
        conn.execute('DROP INDEX IF EXISTS idx_job_queue_priority')
        conn.execute('DROP INDEX IF EXISTS idx_job_queue_type')
        conn.execute('DROP INDEX IF EXISTS idx_job_queue_status')
        
        # Then delete table
        conn.execute('DROP TABLE IF EXISTS job_queue')
        
        print("✅ Dropped job_queue table and all indexes")
    
    def description(self) -> str:
        """Migration description."""
        return "Create job_queue table with status tracking, priorities, and logging support" 