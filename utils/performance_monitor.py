#!/usr/bin/env python3
"""
Performance Monitor for Job Queue System

Performance monitoring system with metrics, profiling
and real-time statistics for production deployment.
"""

import time
import threading
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
from contextlib import contextmanager
import os


@dataclass
class PerformanceMetrics:
    """Metrics snapshot for a specific moment in time."""
    
    timestamp: datetime
    
    # Job Queue Metrics
    total_jobs: int
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    dead_letter_jobs: int
    retry_jobs: int
    
    # Performance Metrics
    avg_job_duration: float
    jobs_per_minute: float
    success_rate: float
    retry_rate: float
    
    # Worker Metrics
    active_workers: int
    busy_workers: int
    idle_workers: int
    worker_utilization: float
    
    # Database Metrics
    db_size: float
    db_query_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class MetricsCollector:
    """Metrics collector for Job Queue System."""
    
    def __init__(self, db_path: str, job_queue_service = None):
        self.db_path = db_path
        self.job_queue_service = job_queue_service
        
        # Metrics history (last 24 hours)
        self.metrics_history: deque = deque(maxlen=1440)  # One record per minute
        
        # Query profiling
        self.query_times: defaultdict = defaultdict(list)
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Background collection
        self._stop_collection = threading.Event()
        self._collection_thread = None
        
    def start_monitoring(self, interval: int = 60):
        """Starts background monitoring with specified interval (seconds)."""
        if self._collection_thread and self._collection_thread.is_alive():
            return
        
        self._stop_collection.clear()
        self._collection_thread = threading.Thread(
            target=self._background_collection,
            args=(interval,),
            daemon=True,
            name="MetricsCollector"
        )
        self._collection_thread.start()
        print(f"Performance monitoring started (interval: {interval}s)")
    
    def stop_monitoring(self):
        """Stops background monitoring."""
        if self._collection_thread:
            self._stop_collection.set()
            self._collection_thread.join(timeout=5)
            print("Performance monitoring stopped")
    
    def _background_collection(self, interval: int):
        """Background thread for metrics collection."""
        while not self._stop_collection.wait(interval):
            try:
                metrics = self.collect_metrics()
                with self._lock:
                    self.metrics_history.append(metrics)
            except Exception as e:
                print(f"Error collecting metrics: {e}")
    
    def collect_metrics(self) -> PerformanceMetrics:
        """Collects all metrics into a single snapshot."""
        timestamp = datetime.utcnow()
        
        # Job Queue Metrics
        job_stats = self._collect_job_stats()
        
        # Performance Metrics
        perf_stats = self._collect_performance_stats()
        
        # Worker Metrics
        worker_stats = self._collect_worker_stats()
        
        # Database Metrics
        db_stats = self._collect_database_stats()
        
        return PerformanceMetrics(
            timestamp=timestamp,
            **job_stats,
            **perf_stats,
            **worker_stats,
            **db_stats
        )
    
    def _collect_job_stats(self) -> Dict[str, int]:
        """Collects job statistics from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count jobs by status
                cursor.execute("""
                    SELECT status, COUNT(*) 
                    FROM job_queue 
                    GROUP BY status
                """)
                
                status_counts = dict(cursor.fetchall())
                
                return {
                    'total_jobs': sum(status_counts.values()),
                    'pending_jobs': status_counts.get('pending', 0),
                    'running_jobs': status_counts.get('running', 0),
                    'completed_jobs': status_counts.get('completed', 0),
                    'failed_jobs': status_counts.get('failed', 0),
                    'dead_letter_jobs': status_counts.get('dead_letter', 0),
                    'retry_jobs': status_counts.get('retrying', 0)
                }
        except Exception as e:
            print(f"Error collecting job stats: {e}")
            return {
                'total_jobs': 0, 'pending_jobs': 0, 'running_jobs': 0,
                'completed_jobs': 0, 'failed_jobs': 0, 'dead_letter_jobs': 0,
                'retry_jobs': 0
            }
    
    def _collect_performance_stats(self) -> Dict[str, float]:
        """Collects performance statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Average job execution duration
                cursor.execute("""
                    SELECT 
                        AVG(
                            CASE 
                                WHEN completed_at IS NOT NULL AND started_at IS NOT NULL 
                                THEN (julianday(completed_at) - julianday(started_at)) * 86400
                                ELSE NULL
                            END
                        ) as avg_duration
                    FROM job_queue 
                    WHERE status = 'completed' 
                    AND completed_at > datetime('now', '-24 hours')
                """)
                
                row = cursor.fetchone()
                avg_duration = row[0] or 0.0
                
                # Jobs per minute (last hour)
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM job_queue 
                    WHERE completed_at > datetime('now', '-1 hour')
                """)
                
                jobs_last_hour = cursor.fetchone()[0] or 0
                jobs_per_minute = jobs_last_hour / 60.0
                
                # Success rate and retry rate
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success,
                        SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END) as retries
                    FROM job_queue 
                    WHERE created_at > datetime('now', '-24 hours')
                """)
                
                row = cursor.fetchone()
                total = row[0] or 0
                success = row[1] or 0
                retries = row[2] or 0
                
                success_rate = (success / total * 100) if total > 0 else 0.0
                retry_rate = (retries / total * 100) if total > 0 else 0.0
                
                return {
                    'avg_job_duration': avg_duration,
                    'jobs_per_minute': jobs_per_minute,
                    'success_rate': success_rate,
                    'retry_rate': retry_rate
                }
        except Exception as e:
            print(f"Error collecting performance stats: {e}")
            return {
                'avg_job_duration': 0.0,
                'jobs_per_minute': 0.0,
                'success_rate': 0.0,
                'retry_rate': 0.0
            }
    
    def _collect_worker_stats(self) -> Dict[str, Any]:
        """Collects worker statistics."""
        try:
            if self.job_queue_service:
                stats = self.job_queue_service.get_queue_stats()
                worker_info = stats.get('workers', {})
                
                active_workers = worker_info.get('total', 0)
                busy_workers = worker_info.get('busy', 0)
                idle_workers = worker_info.get('idle', 0)
                
                utilization = (busy_workers / active_workers * 100) if active_workers > 0 else 0.0
                
                return {
                    'active_workers': active_workers,
                    'busy_workers': busy_workers,
                    'idle_workers': idle_workers,
                    'worker_utilization': utilization
                }
            else:
                return {
                    'active_workers': 0,
                    'busy_workers': 0,
                    'idle_workers': 0,
                    'worker_utilization': 0.0
                }
        except Exception as e:
            print(f"Error collecting worker stats: {e}")
            return {
                'active_workers': 0,
                'busy_workers': 0,
                'idle_workers': 0,
                'worker_utilization': 0.0
            }
    
    def _collect_database_stats(self) -> Dict[str, float]:
        """Collects database metrics."""
        try:
            # Database size
            db_size = 0.0
            if os.path.exists(self.db_path):
                db_size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
            
            # Average query time (last 100 queries)
            with self._lock:
                all_times = []
                for query_type, times in self.query_times.items():
                    all_times.extend(times[-100:])  # Last 100 queries of each type
                
                avg_query_time = sum(all_times) / len(all_times) if all_times else 0.0
            
            return {
                'db_query_time': avg_query_time,
                'db_size': db_size
            }
        except Exception as e:
            print(f"Error collecting database stats: {e}")
            return {
                'db_query_time': 0.0,
                'db_size': 0.0
            }
    
    @contextmanager
    def measure_query_time(self, query_type: str):
        """Context manager for measuring query execution time."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            with self._lock:
                self.query_times[query_type].append(duration)
                # Keep only last 1000 measurements
                if len(self.query_times[query_type]) > 1000:
                    self.query_times[query_type] = self.query_times[query_type][-1000:]
    
    def get_metrics_history(self, hours: int = 24) -> List[PerformanceMetrics]:
        """Returns metrics history for specified number of hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        with self._lock:
            return [
                metrics for metrics in self.metrics_history
                if metrics.timestamp >= cutoff_time
            ]
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """Returns current metrics."""
        return self.collect_metrics()
    
    def export_metrics(self, file_path: str, hours: int = 24):
        """Exports metrics to JSON file."""
        history = self.get_metrics_history(hours)
        
        data = {
            'export_timestamp': datetime.utcnow().isoformat(),
            'hours_covered': hours,
            'total_snapshots': len(history),
            'metrics': [metrics.to_dict() for metrics in history]
        }
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Metrics exported to {file_path} ({len(history)} snapshots)")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Returns performance summary for the last 24 hours."""
        history = self.get_metrics_history(24)
        
        if not history:
            return {'error': 'No metrics data available'}
        
        # Aggregate metrics
        total_jobs = sum(m.total_jobs for m in history) / len(history)
        avg_success_rate = sum(m.success_rate for m in history) / len(history)
        avg_worker_utilization = sum(m.worker_utilization for m in history) / len(history)
        
        latest = history[-1]
        
        return {
            'summary_period': '24 hours',
            'total_snapshots': len(history),
            'latest_metrics': latest.to_dict(),
            'averages': {
                'jobs_processed': total_jobs,
                'success_rate': avg_success_rate,
                'worker_utilization': avg_worker_utilization
            },
            'current_status': {
                'pending_jobs': latest.pending_jobs,
                'running_jobs': latest.running_jobs,
                'active_workers': latest.active_workers
            }
        }


# Singleton instance for global access
_performance_monitor: Optional[MetricsCollector] = None


def get_performance_monitor(db_path: str = None, job_queue_service = None) -> MetricsCollector:
    """Gets singleton instance of performance monitor."""
    global _performance_monitor
    
    if _performance_monitor is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _performance_monitor = MetricsCollector(db_path, job_queue_service)
    
    return _performance_monitor


def start_performance_monitoring(db_path: str, job_queue_service = None, interval: int = 60):
    """Starts performance monitoring with specified parameters."""
    monitor = get_performance_monitor(db_path, job_queue_service)
    monitor.start_monitoring(interval)
    return monitor


def stop_performance_monitoring():
    """Stops performance monitoring."""
    global _performance_monitor
    
    if _performance_monitor:
        _performance_monitor.stop_monitoring()


if __name__ == "__main__":
    # Usage example
    print("🚀 Testing Performance Monitor...")
    
    # Create test monitor
    monitor = MetricsCollector("database.db")
    
    # Collect metrics
    metrics = monitor.collect_metrics()
    print(f"✅ Current metrics collected:")
    print(f"   Total jobs: {metrics.total_jobs}")
    print(f"   DB size: {metrics.db_size:.2f} MB")
    
    # Test query time measurement
    with monitor.measure_query_time("test_query"):
        time.sleep(0.01)  # Simulate query
    
    print(f"✅ Query time measurement working")
    print("🎉 Performance Monitor test completed!") 