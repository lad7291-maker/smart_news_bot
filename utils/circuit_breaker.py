"""
Circuit Breaker для RSS-источников.
P0-003: Graceful degradation RSS-источников.

Алгоритм:
- При ошибке источника увеличиваем счётчик
- После 3 ошибок подряд — источник отключается на 60 минут (DEGRADED)
- При успешном запросе счётчик сбрасывается
- Автоматическое включение через N минут с проверкой
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from utils.db_maintenance import enable_wal_mode
from utils.logger import logger


class SourceStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"  # Временно отключён
    OFFLINE = "offline"  # Долго не отвечает


@dataclass
class SourceHealth:
    """Состояние здоровья одного источника."""

    source_tag: str
    url: str
    status: SourceStatus = SourceStatus.OK
    consecutive_errors: int = 0
    last_error_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    disabled_until: Optional[datetime] = None
    total_requests: int = 0
    total_errors: int = 0
    avg_response_ms: Optional[float] = None


class SourceHealthTracker:
    """Трекер здоровья RSS-источников с circuit breaker."""

    # Пороги
    ERROR_THRESHOLD = 3  # ошибок подряд для перехода в DEGRADED
    DEGRADED_TIMEOUT_MIN = 60  # минуты
    OFFLINE_TIMEOUT_MIN = 360  # 6 часов
    MAX_RESPONSE_MS = 10000  # 10 секунд — долгий ответ

    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        enable_wal_mode(self.conn)
        self._init_database()
        # In-memory кэш состояний
        self._states: Dict[str, SourceHealth] = {}
        self._load_states()
        logger.info(f"SourceHealthTracker инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health (
                source_tag TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT DEFAULT 'ok',
                consecutive_errors INTEGER DEFAULT 0,
                last_error_at TIMESTAMP,
                last_success_at TIMESTAMP,
                disabled_until TIMESTAMP,
                total_requests INTEGER DEFAULT 0,
                total_errors INTEGER DEFAULT 0,
                avg_response_ms REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self.conn.commit()

    def _load_states(self):
        """Загружает состояния из БД в память."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM source_health")
        for row in cursor.fetchall():
            self._states[row["source_tag"]] = SourceHealth(
                source_tag=row["source_tag"],
                url=row["url"],
                status=SourceStatus(row["status"]),
                consecutive_errors=row["consecutive_errors"] or 0,
                last_error_at=self._parse_dt(row["last_error_at"]),
                last_success_at=self._parse_dt(row["last_success_at"]),
                disabled_until=self._parse_dt(row["disabled_until"]),
                total_requests=row["total_requests"] or 0,
                total_errors=row["total_errors"] or 0,
                avg_response_ms=row["avg_response_ms"],
            )

    @staticmethod
    def _parse_dt(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _save_state(self, health: SourceHealth):
        """Сохраняет состояние источника в БД."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO source_health
            (source_tag, url, status, consecutive_errors, last_error_at,
             last_success_at, disabled_until, total_requests, total_errors, avg_response_ms, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_tag) DO UPDATE SET
                url = excluded.url,
                status = excluded.status,
                consecutive_errors = excluded.consecutive_errors,
                last_error_at = excluded.last_error_at,
                last_success_at = excluded.last_success_at,
                disabled_until = excluded.disabled_until,
                total_requests = excluded.total_requests,
                total_errors = excluded.total_errors,
                avg_response_ms = excluded.avg_response_ms,
                updated_at = excluded.updated_at
        """,
            (
                health.source_tag,
                health.url,
                health.status.value,
                health.consecutive_errors,
                health.last_error_at.isoformat() if health.last_error_at else None,
                health.last_success_at.isoformat() if health.last_success_at else None,
                health.disabled_until.isoformat() if health.disabled_until else None,
                health.total_requests,
                health.total_errors,
                health.avg_response_ms,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get_or_create(self, source_tag: str, url: str) -> SourceHealth:
        """Возвращает состояние источника, создаёт если нет."""
        if source_tag not in self._states:
            health = SourceHealth(source_tag=source_tag, url=url)
            self._states[source_tag] = health
            self._save_state(health)
        return self._states[source_tag]

    def can_use(self, source_tag: str, url: str) -> bool:
        """Проверяет, можно ли использовать источник сейчас."""
        health = self.get_or_create(source_tag, url)
        now = datetime.now()

        # Если источник отключён — проверяем, не пора ли включить
        if health.status == SourceStatus.DEGRADED and health.disabled_until:
            if now >= health.disabled_until:
                logger.info(f"🔄 Источник {source_tag} восстановлен из DEGRADED")
                health.status = SourceStatus.OK
                health.consecutive_errors = 0
                health.disabled_until = None
                self._save_state(health)
                return True
            logger.debug(f"⏳ Источник {source_tag} отключён до {health.disabled_until:%H:%M}")
            return False

        if health.status == SourceStatus.OFFLINE and health.disabled_until:
            if now >= health.disabled_until:
                logger.info(f"🔄 Источник {source_tag} восстановлен из OFFLINE")
                health.status = SourceStatus.DEGRADED  # Пробуем осторожно
                health.disabled_until = now + timedelta(minutes=self.DEGRADED_TIMEOUT_MIN)
                self._save_state(health)
                return True
            return False

        return True

    def record_success(self, source_tag: str, url: str, response_ms: Optional[float] = None):
        """Записывает успешный запрос к источнику."""
        health = self.get_or_create(source_tag, url)
        health.total_requests += 1
        health.last_success_at = datetime.now()

        # Сбрасываем ошибки при успехе
        if health.consecutive_errors > 0:
            logger.info(
                f"✅ Источник {source_tag} восстановлен после {health.consecutive_errors} ошибок"
            )
            health.consecutive_errors = 0
            health.status = SourceStatus.OK
            health.disabled_until = None

        # Обновляем среднее время ответа
        if response_ms is not None:
            if health.avg_response_ms is None:
                health.avg_response_ms = response_ms
            else:
                health.avg_response_ms = health.avg_response_ms * 0.8 + response_ms * 0.2

        self._save_state(health)

    def record_error(self, source_tag: str, url: str, error_details: Optional[str] = None):
        """Записывает ошибку запроса к источнику."""
        health = self.get_or_create(source_tag, url)
        health.total_requests += 1
        health.total_errors += 1
        health.consecutive_errors += 1
        health.last_error_at = datetime.now()

        logger.warning(
            f"⚠️ Ошибка источника {source_tag} ({health.consecutive_errors}/{self.ERROR_THRESHOLD}): {error_details or 'unknown'}"
        )

        # Circuit breaker: отключаем после N ошибок подряд
        if health.consecutive_errors >= self.ERROR_THRESHOLD:
            if health.status == SourceStatus.DEGRADED:
                # Повторные ошибки после восстановления — переводим в OFFLINE
                health.status = SourceStatus.OFFLINE
                health.disabled_until = datetime.now() + timedelta(minutes=self.OFFLINE_TIMEOUT_MIN)
                logger.error(
                    f"🚫 Источник {source_tag} переведён в OFFLINE на {self.OFFLINE_TIMEOUT_MIN} мин"
                )
            else:
                health.status = SourceStatus.DEGRADED
                health.disabled_until = datetime.now() + timedelta(
                    minutes=self.DEGRADED_TIMEOUT_MIN
                )
                logger.warning(
                    f"⏸️ Источник {source_tag} переведён в DEGRADED на {self.DEGRADED_TIMEOUT_MIN} мин"
                )

        self._save_state(health)

    def get_all_statuses(self) -> List[Dict]:
        """Возвращает статус всех источников для /health."""
        result = []
        for health in self._states.values():
            result.append(
                {
                    "source_tag": health.source_tag,
                    "status": health.status.value,
                    "consecutive_errors": health.consecutive_errors,
                    "total_requests": health.total_requests,
                    "total_errors": health.total_errors,
                    "disabled_until": (
                        health.disabled_until.isoformat() if health.disabled_until else None
                    ),
                    "avg_response_ms": (
                        round(health.avg_response_ms, 1) if health.avg_response_ms else None
                    ),
                }
            )
        return sorted(result, key=lambda x: x["source_tag"])

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с SourceHealthTracker закрыто")


# Глобальный экземпляр
source_tracker = SourceHealthTracker()
