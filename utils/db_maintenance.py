"""
Обслуживание SQLite-базы данных.
P0-003: WAL-режим, очистка старых данных, VACUUM.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from utils.logger import logger

# Периоды хранения данных (дни)
RETENTION_DAYS = {
    "processed_links": 90,
    "message_stats": 90,
    "delivery_errors": 30,
    "user_sessions": 90,
    "ab_tests": 90,
    "ab_metrics": 90,
    "user_reactions": 90,
    "message_article_map": 90,
}


def enable_wal_mode(conn: sqlite3.Connection) -> None:
    """Включает WAL-режим для лучшей конкурентности."""
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        result = cursor.fetchone()
        if result and result[0] == "wal":
            logger.debug("SQLite WAL mode enabled")
        else:
            logger.warning(f"SQLite WAL mode not enabled, got: {result}")
    except sqlite3.Error as e:
        logger.error(f"Failed to enable WAL mode: {e}")


def run_maintenance(db_path: str = "storage/news_cache.db", vacuum: bool = False) -> dict:
    """
    Запускает обслуживание БД:
    1. Очищает старые записи из таблиц
    2. При vacuum=True — запускает VACUUM для рекламации места

    Returns:
        Словарь с количеством удалённых записей по таблицам
    """
    Path(db_path).parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        cursor = conn.cursor()
        deleted: dict[str, int] = {}

        # Проверяем какие таблицы существуют
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row[0] for row in cursor.fetchall()}

        for table, days in RETENTION_DAYS.items():
            if table not in existing_tables:
                continue

            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            # Определяем колонку с timestamp для каждой таблицы
            timestamp_columns = {
                "processed_links": "processed_at",
                "message_stats": "sent_at",
                "delivery_errors": "occurred_at",
                "user_sessions": "session_date",
                "ab_tests": "sent_at",
                "ab_metrics": "date",
                "user_reactions": "created_at",
                "message_article_map": "sent_at",
            }

            ts_col = timestamp_columns.get(table)
            if not ts_col:
                continue

            # Проверяем, есть ли колонка
            cursor.execute(f"PRAGMA table_info({table});")
            columns = {row[1] for row in cursor.fetchall()}
            if ts_col not in columns:
                continue

            try:
                # Для user_sessions session_date — строка YYYY-MM-DD
                if table == "user_sessions":
                    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    cursor.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff_date,))
                else:
                    cursor.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))

                deleted_count = cursor.rowcount
                deleted[table] = deleted_count
                if deleted_count > 0:
                    logger.info(f"🧹 DB maintenance: deleted {deleted_count} old rows from {table}")
            except sqlite3.Error as e:
                logger.error(f"Failed to clean {table}: {e}")

        if vacuum and deleted:
            try:
                cursor.execute("VACUUM;")
                logger.info("🧹 DB maintenance: VACUUM completed")
            except sqlite3.Error as e:
                logger.error(f"VACUUM failed: {e}")

        conn.commit()
        return deleted

    except sqlite3.Error as e:
        logger.error(f"DB maintenance failed: {e}")
        return {}
    finally:
        conn.close()


def get_db_stats(db_path: str = "storage/news_cache.db") -> dict:
    """Возвращает статистику по таблицам БД."""
    Path(db_path).parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        stats = {}
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                stats[table] = count
            except sqlite3.Error:
                stats[table] = -1

        # Размер файла БД
        db_size = Path(db_path).stat().st_size
        stats["_db_size_mb"] = round(db_size / (1024 * 1024), 2)

        return stats
    finally:
        conn.close()
