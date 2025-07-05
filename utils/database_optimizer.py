#!/usr/bin/env python3
"""
Database Optimizer for Job Queue System

Database optimization system with connection pooling, query optimization,
and database maintenance for production deployment.
"""

import sqlite3
import threading
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from contextlib import contextmanager
from queue import Queue, Empty
import logging


class ConnectionPool:
    """SQLite Connection Pool for database access optimization."""
    
    def __init__(self, db_path: str, pool_size: int = 10, timeout: float = 30.0):
        """
        Initializes connection pool.
        
        Args:
            db_path: Path to SQLite database
            pool_size: Maximum number of connections in pool
            timeout: Timeout for getting connection from pool (seconds)
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        
        # Connection pool
        self._pool = Queue(maxsize=pool_size)
        self._all_connections = []
        self._lock = threading.RLock()
        
        # Connection statistics
        self.total_connections_created = 0
        self.active_connections = 0
        self.peak_connections = 0
        
        # Performance optimization settings
        self._connection_settings = {
            'journal_mode': 'WAL',  # Write-Ahead Logging for better concurrency
            'synchronous': 'NORMAL',  # Balance between safety and performance
            'cache_size': -64000,  # 64MB cache size (negative = KB)
            'temp_store': 'MEMORY',  # Temporary tables in memory
            'mmap_size': 268435456,  # 256MB memory-mapped I/O
            'optimize': True  # Automatic query optimization
        }
        
        # Initialize pool
        self._initialize_pool()
        
        logging.info(f"Connection pool initialized (size: {pool_size}, db: {db_path})")
    
    def _initialize_pool(self):
        """Initializes connections in pool."""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
    
    def _create_connection(self) -> sqlite3.Connection:
        """Creates new optimized SQLite connection."""
        try:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # Allow multi-threading
                timeout=self.timeout
            )
            
            # Apply optimization settings
            self._apply_optimization_settings(conn)
            
            # Enable row factory for convenient data access
            conn.row_factory = sqlite3.Row
            
            with self._lock:
                self.total_connections_created += 1
                self._all_connections.append(conn)
            
            return conn
            
        except Exception as e:
            logging.error(f"Failed to create database connection: {e}")
            raise
    
    def _apply_optimization_settings(self, conn: sqlite3.Connection):
        """Applies optimization settings to connection."""
        cursor = conn.cursor()
        
        try:
            # Apply each optimization setting
            for setting, value in self._connection_settings.items():
                if setting == 'optimize':
                    continue  # Handle separately
                
                if isinstance(value, str):
                    cursor.execute(f"PRAGMA {setting} = {value}")
                else:
                    cursor.execute(f"PRAGMA {setting} = {value}")
            
            # Run auto-optimization
            if self._connection_settings.get('optimize', False):
                cursor.execute("PRAGMA optimize")
            
            conn.commit()
            
        except Exception as e:
            logging.warning(f"Failed to apply some optimization settings: {e}")
        finally:
            cursor.close()
    
    @contextmanager
    def get_connection(self):
        """Context manager for getting connection from pool."""
        conn = None
        start_time = time.time()
        
        try:
            # Get connection from pool
            try:
                conn = self._pool.get(timeout=self.timeout)
            except Empty:
                raise TimeoutError(f"Failed to get connection from pool within {self.timeout}s")
            
            # Update statistics
            with self._lock:
                self.active_connections += 1
                self.peak_connections = max(self.peak_connections, self.active_connections)
            
            # Check if connection is still alive
            try:
                conn.execute("SELECT 1").fetchone()
            except sqlite3.Error:
                # Connection is dead, create new one
                conn.close()
                conn = self._create_connection()
            
            yield conn
            
        finally:
            # Return connection to pool
            if conn:
                try:
                    # Rollback any uncommitted transactions
                    conn.rollback()
                    
                    # Return to pool
                    self._pool.put(conn)
                    
                except Exception as e:
                    logging.error(f"Error returning connection to pool: {e}")
                    # If can't return, create new connection for pool
                    try:
                        new_conn = self._create_connection()
                        self._pool.put(new_conn)
                    except Exception:
                        pass  # Pool will be smaller, but better than crash
                
                # Update statistics
                with self._lock:
                    self.active_connections -= 1
            
            # Log slow queries
            duration = time.time() - start_time
            if duration > 1.0:  # More than 1 second
                logging.warning(f"Slow database operation: {duration:.2f}s")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Returns connection pool statistics."""
        with self._lock:
            return {
                'pool_size': self.pool_size,
                'available_connections': self._pool.qsize(),
                'active_connections': self.active_connections,
                'total_created': self.total_connections_created,
                'peak_connections': self.peak_connections,
                'settings': self._connection_settings.copy()
            }
    
    def close_all(self):
        """Closes all connections in pool."""
        with self._lock:
            # Close all connections
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            
            # Clear pool
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except (Empty, Exception):
                    break
            
            self._all_connections.clear()
            self.active_connections = 0
            
        logging.info("All database connections closed")


class DatabaseOptimizer:
    """Main class for database optimization and maintenance."""
    
    def __init__(self, db_path: str, pool_size: int = 10):
        """
        Initializes database optimizer.
        
        Args:
            db_path: Path to SQLite database
            pool_size: Connection pool size
        """
        self.db_path = db_path
        self.connection_pool = ConnectionPool(db_path, pool_size)
        
        # Query optimization cache
        self._query_cache = {}
        self._query_stats = {}
        
        # Maintenance settings
        self.maintenance_interval = 3600  # 1 hour
        self.last_maintenance = datetime.utcnow()
        
        logging.info(f"Database optimizer initialized for {db_path}")
    
    @contextmanager
    def get_optimized_connection(self):
        """Gets optimized connection with automatic query monitoring."""
        with self.connection_pool.get_connection() as conn:
            yield OptimizedConnection(conn, self)
    
    def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, 
                     fetch_all: bool = False) -> Any:
        """
        Executes optimized query with automatic caching and monitoring.
        
        Args:
            query: SQL query
            params: Query parameters
            fetch_one: Return only one row
            fetch_all: Return all rows
            
        Returns:
            Query result based on fetch parameters
        """
        start_time = time.time()
        query_hash = hash((query, params))
        
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Execute query
                cursor.execute(query, params)
                
                # Get result
                result = None
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                
                # Commit if needed
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    conn.commit()
                
                return result
                
        except Exception as e:
            logging.error(f"Query execution failed: {e}, Query: {query[:100]}...")
            raise
        finally:
            # Record query statistics
            duration = time.time() - start_time
            self._record_query_stats(query, duration)
    
    def _record_query_stats(self, query: str, duration: float):
        """Records query statistics for performance monitoring."""
        query_type = query.strip().split()[0].upper()
        
        if query_type not in self._query_stats:
            self._query_stats[query_type] = {
                'count': 0,
                'total_time': 0.0,
                'max_time': 0.0,
                'min_time': float('inf')
            }
        
        stats = self._query_stats[query_type]
        stats['count'] += 1
        stats['total_time'] += duration
        stats['max_time'] = max(stats['max_time'], duration)
        stats['min_time'] = min(stats['min_time'], duration)
        
        # Log very slow queries
        if duration > 5.0:
            logging.warning(f"Very slow query ({duration:.2f}s): {query[:200]}...")
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Returns query performance statistics."""
        stats = {}
        
        for query_type, data in self._query_stats.items():
            if data['count'] > 0:
                stats[query_type] = {
                    'count': data['count'],
                    'avg_time': data['total_time'] / data['count'],
                    'max_time': data['max_time'],
                    'min_time': data['min_time'] if data['min_time'] != float('inf') else 0.0,
                    'total_time': data['total_time']
                }
        
        return stats
    
    def run_maintenance(self, force: bool = False) -> Dict[str, Any]:
        """
        Runs database maintenance tasks.
        
        Args:
            force: Force maintenance even if interval hasn't passed
            
        Returns:
            Dictionary with maintenance results
        """
        now = datetime.utcnow()
        
        # Check if maintenance should be run
        if not force and (now - self.last_maintenance).seconds < self.maintenance_interval:
            return {'skipped': True, 'reason': 'Too early for maintenance'}
        
        results = {}
        start_time = time.time()
        
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. VACUUM to free space
                logging.info("Running VACUUM...")
                db_size_before = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                cursor.execute("VACUUM")
                db_size_after = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                results['vacuum'] = {
                    'size_before_mb': db_size_before / (1024 * 1024),
                    'size_after_mb': db_size_after / (1024 * 1024),
                    'space_freed_mb': (db_size_before - db_size_after) / (1024 * 1024)
                }
                
                # 2. ANALYZE to update statistics
                logging.info("Running ANALYZE...")
                cursor.execute("ANALYZE")
                
                # 3. OPTIMIZE to update query planner statistics
                logging.info("Running OPTIMIZE...")
                cursor.execute("PRAGMA optimize")
                
                # 4. Clean up old completed tasks (older than 7 days)
                logging.info("Cleaning up old completed jobs...")
                cutoff_date = now - timedelta(days=7)
                cursor.execute("""
                    DELETE FROM job_queue 
                    WHERE status = 'completed' 
                    AND completed_at < ?
                """, (cutoff_date.isoformat(),))
                
                cleaned_jobs = cursor.rowcount
                results['cleanup'] = {'removed_jobs': cleaned_jobs}
                
                # 5. Check integrity
                logging.info("Checking database integrity...")
                cursor.execute("PRAGMA integrity_check")
                integrity_result = cursor.fetchone()
                results['integrity'] = {'status': integrity_result[0] if integrity_result else 'unknown'}
                
                conn.commit()
                
                # Update last maintenance time
                self.last_maintenance = now
                
                results['success'] = True
                results['duration'] = time.time() - start_time
                
                logging.info(f"Database maintenance completed in {results['duration']:.2f}s")
                
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            logging.error(f"Database maintenance failed: {e}")
        
        return results
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Returns comprehensive database statistics."""
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Database size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                # Table statistics
                cursor.execute("""
                    SELECT name, COUNT(*) as row_count
                    FROM sqlite_master 
                    WHERE type='table' AND name != 'sqlite_sequence'
                """)
                table_info = cursor.fetchall()
                
                # Page statistics
                cursor.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]
                
                cursor.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                
                cursor.execute("PRAGMA freelist_count")
                free_pages = cursor.fetchone()[0]
                
                # WAL file info
                wal_file = self.db_path + '-wal'
                wal_size = os.path.getsize(wal_file) if os.path.exists(wal_file) else 0
                
                return {
                    'database_size_mb': db_size / (1024 * 1024),
                    'wal_size_mb': wal_size / (1024 * 1024),
                    'page_count': page_count,
                    'page_size': page_size,
                    'free_pages': free_pages,
                    'tables': {row[0]: row[1] for row in table_info},
                    'connection_pool': self.connection_pool.get_pool_stats(),
                    'query_stats': self.get_query_stats()
                }
                
        except Exception as e:
            logging.error(f"Failed to get database stats: {e}")
            return {'error': str(e)}
    
    def close(self):
        """Closes database optimizer and all connections."""
        self.connection_pool.close_all()
        logging.info("Database optimizer closed")


class OptimizedConnection:
    """Wrapper for database connection with automatic query monitoring."""
    
    def __init__(self, connection: sqlite3.Connection, optimizer: DatabaseOptimizer):
        self.connection = connection
        self.optimizer = optimizer
        self._start_time = time.time()
    
    def execute(self, query: str, params: tuple = ()):
        """Executes query with automatic monitoring."""
        start_time = time.time()
        try:
            cursor = self.connection.cursor()
            result = cursor.execute(query, params)
            return result
        finally:
            duration = time.time() - start_time
            self.optimizer._record_query_stats(query, duration)
    
    def commit(self):
        """Commits transaction."""
        self.connection.commit()
    
    def rollback(self):
        """Rolls back transaction."""
        self.connection.rollback()
    
    def __getattr__(self, name):
        """Delegates attribute access to underlying connection."""
        return getattr(self.connection, name)


# Global optimizer instance for singleton pattern
_database_optimizer: Optional[DatabaseOptimizer] = None


def get_database_optimizer(db_path: str = None, pool_size: int = 10) -> DatabaseOptimizer:
    """Gets singleton instance of database optimizer."""
    global _database_optimizer
    
    if _database_optimizer is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _database_optimizer = DatabaseOptimizer(db_path, pool_size)
    
    return _database_optimizer


def initialize_database_optimization(db_path: str, pool_size: int = 10) -> DatabaseOptimizer:
    """Initializes database optimization system."""
    optimizer = get_database_optimizer(db_path, pool_size)
    logging.info(f"Database optimization initialized (pool_size: {pool_size})")
    return optimizer


if __name__ == "__main__":
    # Usage example
    print("🚀 Testing Database Optimizer...")
    
    # Initialize optimizer
    optimizer = DatabaseOptimizer("database.db", pool_size=5)
    
    # Test connection
    with optimizer.get_optimized_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM job_queue")
        count = cursor.fetchone()
        print(f"✅ Connection test: {count[0] if count else 0} jobs in queue")
    
    # Get statistics
    stats = optimizer.get_database_stats()
    print(f"✅ Database stats: {stats['database_size_mb']:.2f} MB")
    
    # Test maintenance
    maintenance_result = optimizer.run_maintenance(force=True)
    print(f"✅ Maintenance test: {maintenance_result['success']}")
    
    # Close
    optimizer.close()
    print("🎉 Database Optimizer test completed!") 