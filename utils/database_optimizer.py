#!/usr/bin/env python3
"""
Database Optimizer for Job Queue System

Система оптимизации базы данных с connection pooling, query optimization,
и database maintenance для production deployment.
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
    """SQLite Connection Pool для оптимизации database access."""
    
    def __init__(self, db_path: str, pool_size: int = 10, timeout: float = 30.0):
        """
        Инициализирует connection pool.
        
        Args:
            db_path: Путь к SQLite database
            pool_size: Максимальное количество соединений в pool
            timeout: Timeout для получения соединения из pool (секунды)
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
            'journal_mode': 'WAL',  # Write-Ahead Logging для better concurrency
            'synchronous': 'NORMAL',  # Balance между safety и performance
            'cache_size': -64000,  # 64MB cache size (negative = KB)
            'temp_store': 'MEMORY',  # Временные таблицы в memory
            'mmap_size': 268435456,  # 256MB memory-mapped I/O
            'optimize': True  # Automatic query optimization
        }
        
        # Инициализируем pool
        self._initialize_pool()
        
        logging.info(f"Connection pool initialized (size: {pool_size}, db: {db_path})")
    
    def _initialize_pool(self):
        """Инициализирует connections в pool."""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
    
    def _create_connection(self) -> sqlite3.Connection:
        """Создает новое optimized SQLite соединение."""
        try:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # Разрешаем multi-threading
                timeout=self.timeout
            )
            
            # Применяем optimization settings
            self._apply_optimization_settings(conn)
            
            # Включаем row factory для удобного доступа к данным
            conn.row_factory = sqlite3.Row
            
            with self._lock:
                self.total_connections_created += 1
                self._all_connections.append(conn)
            
            return conn
            
        except Exception as e:
            logging.error(f"Failed to create database connection: {e}")
            raise
    
    def _apply_optimization_settings(self, conn: sqlite3.Connection):
        """Применяет optimization settings к соединению."""
        cursor = conn.cursor()
        
        try:
            # Применяем каждую optimization setting
            for setting, value in self._connection_settings.items():
                if setting == 'optimize':
                    continue  # Обрабатываем отдельно
                
                if isinstance(value, str):
                    cursor.execute(f"PRAGMA {setting} = {value}")
                else:
                    cursor.execute(f"PRAGMA {setting} = {value}")
            
            # Запускаем автооптимизацию
            if self._connection_settings.get('optimize', False):
                cursor.execute("PRAGMA optimize")
            
            conn.commit()
            
        except Exception as e:
            logging.warning(f"Failed to apply some optimization settings: {e}")
        finally:
            cursor.close()
    
    @contextmanager
    def get_connection(self):
        """Context manager для получения соединения из pool."""
        conn = None
        start_time = time.time()
        
        try:
            # Получаем соединение из pool
            try:
                conn = self._pool.get(timeout=self.timeout)
            except Empty:
                raise TimeoutError(f"Failed to get connection from pool within {self.timeout}s")
            
            # Обновляем статистику
            with self._lock:
                self.active_connections += 1
                self.peak_connections = max(self.peak_connections, self.active_connections)
            
            # Проверяем, что соединение еще живо
            try:
                conn.execute("SELECT 1").fetchone()
            except sqlite3.Error:
                # Соединение мертво, создаем новое
                conn.close()
                conn = self._create_connection()
            
            yield conn
            
        finally:
            # Возвращаем соединение в pool
            if conn:
                try:
                    # Rollback любых незакоммиченных транзакций
                    conn.rollback()
                    
                    # Возвращаем в pool
                    self._pool.put(conn)
                    
                except Exception as e:
                    logging.error(f"Error returning connection to pool: {e}")
                    # Если не можем вернуть, создаем новое соединение для pool
                    try:
                        new_conn = self._create_connection()
                        self._pool.put(new_conn)
                    except Exception:
                        pass  # Pool будет меньше, но это лучше чем crash
                
                # Обновляем статистику
                with self._lock:
                    self.active_connections -= 1
            
            # Логируем медленные запросы
            duration = time.time() - start_time
            if duration > 1.0:  # Более 1 секунды
                logging.warning(f"Slow database operation: {duration:.2f}s")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Возвращает статистику connection pool."""
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
        """Закрывает все соединения в pool."""
        with self._lock:
            # Закрываем все соединения
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            
            # Очищаем pool
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
    """Главный класс для database optimization и maintenance."""
    
    def __init__(self, db_path: str, pool_size: int = 10):
        """
        Инициализирует database optimizer.
        
        Args:
            db_path: Путь к SQLite database
            pool_size: Размер connection pool
        """
        self.db_path = db_path
        self.connection_pool = ConnectionPool(db_path, pool_size)
        
        # Query optimization cache
        self._query_cache = {}
        self._query_stats = {}
        
        # Maintenance settings
        self.maintenance_interval = 3600  # 1 час
        self.last_maintenance = datetime.utcnow()
        
        logging.info(f"Database optimizer initialized for {db_path}")
    
    @contextmanager
    def get_optimized_connection(self):
        """Получает optimized соединение с automatic query monitoring."""
        with self.connection_pool.get_connection() as conn:
            yield OptimizedConnection(conn, self)
    
    def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, 
                     fetch_all: bool = False) -> Any:
        """
        Выполняет optimized query с automatic caching и monitoring.
        
        Args:
            query: SQL запрос
            params: Параметры для запроса
            fetch_one: Вернуть только одну строку
            fetch_all: Вернуть все строки
            
        Returns:
            Результат запроса или None
        """
        start_time = time.time()
        query_hash = hash((query, params))
        
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Выполняем запрос
                cursor.execute(query, params)
                
                # Получаем результат
                result = None
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                
                # Коммитим если нужно
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    conn.commit()
                
                return result
                
        except Exception as e:
            logging.error(f"Query execution failed: {e}, Query: {query[:100]}...")
            raise
        finally:
            # Записываем статистику запроса
            duration = time.time() - start_time
            self._record_query_stats(query, duration)
    
    def _record_query_stats(self, query: str, duration: float):
        """Записывает статистику выполнения запроса."""
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
        
        # Логируем очень медленные запросы
        if duration > 5.0:
            logging.warning(f"Very slow query ({duration:.2f}s): {query[:200]}...")
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Возвращает статистику выполнения запросов."""
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
        Запускает database maintenance процедуры.
        
        Args:
            force: Принудительно запустить maintenance
            
        Returns:
            Результаты maintenance
        """
        now = datetime.utcnow()
        
        # Проверяем, нужно ли запускать maintenance
        if not force and (now - self.last_maintenance).seconds < self.maintenance_interval:
            return {'skipped': True, 'reason': 'Too early for maintenance'}
        
        results = {}
        start_time = time.time()
        
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. VACUUM для освобождения места
                logging.info("Running VACUUM...")
                db_size_before = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                cursor.execute("VACUUM")
                db_size_after = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                results['vacuum'] = {
                    'size_before_mb': db_size_before / (1024 * 1024),
                    'size_after_mb': db_size_after / (1024 * 1024),
                    'space_freed_mb': (db_size_before - db_size_after) / (1024 * 1024)
                }
                
                # 2. ANALYZE для обновления статистики
                logging.info("Running ANALYZE...")
                cursor.execute("ANALYZE")
                
                # 3. OPTIMIZE для обновления query planner statistics
                logging.info("Running OPTIMIZE...")
                cursor.execute("PRAGMA optimize")
                
                # 4. Очистка старых completed задач (старше 7 дней)
                logging.info("Cleaning up old completed jobs...")
                cutoff_date = now - timedelta(days=7)
                cursor.execute("""
                    DELETE FROM job_queue 
                    WHERE status = 'completed' 
                    AND completed_at < ?
                """, (cutoff_date.isoformat(),))
                
                cleaned_jobs = cursor.rowcount
                results['cleanup'] = {'removed_jobs': cleaned_jobs}
                
                # 5. Проверка integrity
                logging.info("Checking database integrity...")
                cursor.execute("PRAGMA integrity_check")
                integrity_result = cursor.fetchone()
                results['integrity'] = {'status': integrity_result[0] if integrity_result else 'unknown'}
                
                conn.commit()
                
                # Обновляем время последнего maintenance
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
        """Возвращает полную статистику database."""
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Размер базы данных
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                # Статистика таблиц
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
        """Закрывает все соединения и очищает ресурсы."""
        self.connection_pool.close_all()
        logging.info("Database optimizer closed")


class OptimizedConnection:
    """Wrapper для database connection с automatic monitoring."""
    
    def __init__(self, connection: sqlite3.Connection, optimizer: DatabaseOptimizer):
        self.connection = connection
        self.optimizer = optimizer
        self._start_time = time.time()
    
    def execute(self, query: str, params: tuple = ()):
        """Выполняет query с monitoring."""
        start_time = time.time()
        try:
            cursor = self.connection.cursor()
            result = cursor.execute(query, params)
            return result
        finally:
            duration = time.time() - start_time
            self.optimizer._record_query_stats(query, duration)
    
    def commit(self):
        """Коммитит транзакцию."""
        self.connection.commit()
    
    def rollback(self):
        """Откатывает транзакцию."""
        self.connection.rollback()
    
    def __getattr__(self, name):
        """Проксирует все остальные методы к оригинальному connection."""
        return getattr(self.connection, name)


# Singleton instance для global access
_database_optimizer: Optional[DatabaseOptimizer] = None


def get_database_optimizer(db_path: str = None, pool_size: int = 10) -> DatabaseOptimizer:
    """Получает singleton instance database optimizer."""
    global _database_optimizer
    
    if _database_optimizer is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _database_optimizer = DatabaseOptimizer(db_path, pool_size)
    
    return _database_optimizer


def initialize_database_optimization(db_path: str, pool_size: int = 10) -> DatabaseOptimizer:
    """Инициализирует database optimization."""
    optimizer = get_database_optimizer(db_path, pool_size)
    logging.info(f"Database optimization initialized (pool_size: {pool_size})")
    return optimizer


if __name__ == "__main__":
    # Пример использования
    print("🚀 Testing Database Optimizer...")
    
    # Инициализируем optimizer
    optimizer = DatabaseOptimizer("database.db", pool_size=5)
    
    # Тестируем соединение
    with optimizer.get_optimized_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM job_queue")
        count = cursor.fetchone()
        print(f"✅ Connection test: {count[0] if count else 0} jobs in queue")
    
    # Получаем статистику
    stats = optimizer.get_database_stats()
    print(f"✅ Database stats: {stats['database_size_mb']:.2f} MB")
    
    # Тестируем maintenance
    maintenance_result = optimizer.run_maintenance(force=True)
    print(f"✅ Maintenance test: {maintenance_result['success']}")
    
    # Закрываем
    optimizer.close()
    print("🎉 Database Optimizer test completed!") 