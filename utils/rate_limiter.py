"""
Модуль rate limiting для админ-команд.
P1-003: Rate limiting на админ-команды.

Предотвращает спам команд вроде /post_now, который приводит к FLOOD_WAIT.
"""

import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from utils.db_maintenance import enable_wal_mode
from utils.logger import logger


class RateLimiter:
    """Rate limiter с хранением состояния в SQLite (переживает перезапуск)."""

    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        enable_wal_mode(self.conn)
        self._init_database()
        logger.info(f"RateLimiter инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_state (
                user_id TEXT NOT NULL,
                command TEXT NOT NULL,
                call_count INTEGER DEFAULT 1,
                window_start TIMESTAMP NOT NULL,
                last_call_at TIMESTAMP NOT NULL,
                PRIMARY KEY (user_id, command)
            )
        """
        )
        self.conn.commit()

    def is_allowed(
        self, user_id: str, command: str, max_calls: int, window_seconds: int
    ) -> tuple[bool, Optional[int]]:
        """
        Проверяет, разрешён ли вызов команды.
        Возвращает (allowed, retry_after_seconds).
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT call_count, window_start, last_call_at
                FROM rate_limit_state
                WHERE user_id = ? AND command = ?
            """,
                (user_id, command),
            )
            row = cursor.fetchone()

            if row is None:
                # Первый вызов
                cursor.execute(
                    """
                    INSERT INTO rate_limit_state (user_id, command, call_count, window_start, last_call_at)
                    VALUES (?, ?, 1, ?, ?)
                """,
                    (user_id, command, now.isoformat(), now.isoformat()),
                )
                self.conn.commit()
                return True, None

            stored_window_start = datetime.fromisoformat(row["window_start"])
            call_count = row["call_count"]

            if stored_window_start < window_start:
                # Окно истекло — сбрасываем
                cursor.execute(
                    """
                    UPDATE rate_limit_state
                    SET call_count = 1, window_start = ?, last_call_at = ?
                    WHERE user_id = ? AND command = ?
                """,
                    (now.isoformat(), now.isoformat(), user_id, command),
                )
                self.conn.commit()
                return True, None

            if call_count >= max_calls:
                # Лимит исчерпан
                retry_after = int(
                    (stored_window_start + timedelta(seconds=window_seconds) - now).total_seconds()
                )
                return False, max(1, retry_after)

            # Увеличиваем счётчик
            cursor.execute(
                """
                UPDATE rate_limit_state
                SET call_count = call_count + 1, last_call_at = ?
                WHERE user_id = ? AND command = ?
            """,
                (now.isoformat(), user_id, command),
            )
            self.conn.commit()
            return True, None

        except sqlite3.Error as e:
            logger.error(f"Ошибка rate limiter: {e}")
            # При ошибке БД разрешаем вызов (fail open)
            return True, None

    def reset(self, user_id: str, command: str) -> bool:
        """Сбрасывает лимит для пользователя и команды."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM rate_limit_state WHERE user_id = ? AND command = ?",
                (user_id, command),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка сброса rate limit: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с RateLimiter закрыто")


# Глобальный экземпляр
rate_limiter = RateLimiter()


def rate_limit(calls: int = 3, period: int = 60):
    """
    Декоратор для ограничения частоты вызовов команд.

    Args:
        calls: Максимальное количество вызовов за период
        period: Период в секундах
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(message, *args, **kwargs):
            user_id = str(getattr(message, "from_user", getattr(message, "user", None)).id)
            command = func.__name__

            allowed, retry_after = rate_limiter.is_allowed(user_id, command, calls, period)
            if not allowed:
                await message.answer(
                    f"⏳ Слишком часто! Подождите {retry_after} секунд перед следующим вызовом."
                )
                logger.warning(f"Rate limit: {user_id} /{command} blocked, retry in {retry_after}s")
                return None

            return await func(message, *args, **kwargs)

        return async_wrapper

    return decorator
