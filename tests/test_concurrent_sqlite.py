"""
Tests for concurrent SQLite writes with WAL mode.
P0-003: Проверка отсутствия database is locked при параллельной записи.
"""

import sqlite3
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from utils.db_maintenance import enable_wal_mode


class TestConcurrentSQLite:
    def test_wal_mode_enabled(self):
        """WAL-режим должен включаться при вызове enable_wal_mode."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            enable_wal_mode(conn)

            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            assert mode == "wal", f"Expected 'wal', got '{mode}'"
            conn.close()

    def test_concurrent_writes_no_lock_error(self):
        """10 потоков пишут одновременно — не должно быть database is locked."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Создаём таблицу с WAL
            conn = sqlite3.connect(str(db_path))
            enable_wal_mode(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS test_writes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER,
                    value TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()
            conn.close()

            errors = []
            success_count = [0]

            def writer(thread_id: int):
                try:
                    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10.0)
                    for i in range(20):
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO test_writes (thread_id, value) VALUES (?, ?)",
                            (thread_id, f"value_{thread_id}_{i}"),
                        )
                        conn.commit()
                        time.sleep(0.001)  # Небольшая задержка для переплетения
                    success_count[0] += 1
                    conn.close()
                except Exception as e:
                    errors.append((thread_id, str(e)))

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            # Проверяем результаты
            assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
            assert success_count[0] == 10, f"Expected 10 successful writers, got {success_count[0]}"

            # Проверяем, что все записи на месте
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test_writes;")
            count = cursor.fetchone()[0]
            assert count == 200, f"Expected 200 rows, got {count}"
            conn.close()

    def test_concurrent_read_while_write(self):
        """Чтение во время записи не блокируется в WAL-режиме."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            conn = sqlite3.connect(str(db_path))
            enable_wal_mode(conn)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS test_data (id INTEGER PRIMARY KEY, value TEXT);"
            )
            cursor.execute("INSERT INTO test_data (value) VALUES ('initial');")
            conn.commit()
            conn.close()

            read_errors = []
            read_results = []

            def reader():
                try:
                    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5.0)
                    for _ in range(50):
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM test_data;")
                        read_results.append(cursor.fetchone()[0])
                        time.sleep(0.002)
                    conn.close()
                except Exception as e:
                    read_errors.append(str(e))

            def writer():
                try:
                    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5.0)
                    for i in range(50):
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO test_data (value) VALUES (?)", (f"val_{i}",))
                        conn.commit()
                        time.sleep(0.002)
                    conn.close()
                except Exception:
                    pass  # Writer errors handled separately if needed

            t_reader = threading.Thread(target=reader)
            t_writer = threading.Thread(target=writer)
            t_reader.start()
            t_writer.start()
            t_reader.join(timeout=30)
            t_writer.join(timeout=30)

            assert len(read_errors) == 0, f"Read errors: {read_errors}"
            assert len(read_results) == 50, f"Expected 50 reads, got {len(read_results)}"
