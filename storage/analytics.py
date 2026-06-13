"""
Модуль аналитики и метрик доставки для Smart News Bot.
P0-001: Система аналитики и метрик доставки.

Таблицы:
- message_stats: статистика отправленных сообщений
- delivery_errors: ошибки доставки (включая FLOOD_WAIT)
- user_sessions: сессии пользователей для DAU/MAU
"""

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.db_maintenance import enable_wal_mode
from utils.logger import logger


@dataclass
class MessageStat:
    """Запись о отправленном сообщении."""

    message_id: Optional[int]
    chat_id: str
    article_link: str
    article_title: str
    source_tag: str
    score: int
    sent_at: datetime
    delivered: bool
    has_image: bool
    is_fallback_image: bool


@dataclass
class DeliveryError:
    """Запись об ошибке доставки."""

    error_type: str
    error_code: Optional[int]
    article_link: Optional[str]
    article_title: Optional[str]
    occurred_at: datetime
    details: Optional[str] = None


class AnalyticsManager:
    """Менеджер аналитики: метрики доставки, DAU/MAU, CTR, ошибки."""

    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        enable_wal_mode(self.conn)
        self._init_database()
        logger.info(f"AnalyticsManager инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()

        # --- Статистика отправленных сообщений ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                chat_id TEXT NOT NULL,
                article_link TEXT NOT NULL,
                article_title TEXT,
                source_tag TEXT,
                score INTEGER DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered INTEGER DEFAULT 1,
                has_image INTEGER DEFAULT 0,
                is_fallback_image INTEGER DEFAULT 0
            )
        """
        )

        # --- Ошибки доставки ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                error_code INTEGER,
                article_link TEXT,
                article_title TEXT,
                details TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- Сессии пользователей (для DAU/MAU) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_date TEXT NOT NULL,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interactions_count INTEGER DEFAULT 1,
                UNIQUE(user_id, session_date)
            )
        """
        )

        # --- AI usage и стоимость ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT,
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                article_title TEXT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- Индексы для производительности ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_stats_sent_at ON message_stats(sent_at)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_msg_stats_source ON message_stats(source_tag)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_errors_occurred ON delivery_errors(occurred_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_date ON user_sessions(session_date)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_provider ON ai_usage(provider)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_date ON ai_usage(used_at)")

        self.conn.commit()

    # === Запись данных ===

    def record_message_sent(
        self,
        message_id: Optional[int],
        chat_id: str,
        article_link: str,
        article_title: str = "",
        source_tag: str = "",
        score: int = 0,
        delivered: bool = True,
        has_image: bool = False,
        is_fallback_image: bool = False,
    ) -> bool:
        """Записывает факт отправки сообщения."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO message_stats
                (message_id, chat_id, article_link, article_title, source_tag, score,
                 sent_at, delivered, has_image, is_fallback_image)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    message_id,
                    chat_id,
                    article_link,
                    article_title,
                    source_tag,
                    score,
                    datetime.now().isoformat(),
                    1 if delivered else 0,
                    1 if has_image else 0,
                    1 if is_fallback_image else 0,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка записи message_stats: {e}")
            return False

    def record_delivery_error(
        self,
        error_type: str,
        error_code: Optional[int] = None,
        article_link: Optional[str] = None,
        article_title: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Записывает ошибку доставки (включая FLOOD_WAIT, RetryAfter и др.)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO delivery_errors
                (error_type, error_code, article_link, article_title, details, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    error_type,
                    error_code,
                    article_link,
                    article_title,
                    details,
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка записи delivery_errors: {e}")
            return False

    def record_user_session(self, user_id: str) -> bool:
        """Записывает или обновляет сессию пользователя для DAU/MAU."""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_sessions (user_id, session_date, first_seen_at, last_active_at, interactions_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(user_id, session_date) DO UPDATE SET
                    last_active_at = ?,
                    interactions_count = interactions_count + 1
            """,
                (user_id, today, now, now, now),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка записи user_sessions: {e}")
            return False

    # === Аналитические запросы ===

    def get_dau(self, days: int = 1) -> int:
        """Возвращает количество уникальных активных пользователей за N дней."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) as dau
                FROM user_sessions
                WHERE session_date >= ?
            """,
                (since,),
            )
            row = cursor.fetchone()
            return row["dau"] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта DAU: {e}")
            return 0

    def get_mau(self) -> int:
        """Возвращает MAU (30 дней)."""
        return self.get_dau(days=30)

    def get_delivery_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Статистика доставки за последние N часов."""
        since = datetime.now() - timedelta(hours=hours)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_sent,
                    SUM(CASE WHEN delivered = 1 THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN has_image = 1 THEN 1 ELSE 0 END) as with_image,
                    SUM(CASE WHEN is_fallback_image = 1 THEN 1 ELSE 0 END) as fallback_images
                FROM message_stats
                WHERE sent_at >= ?
            """,
                (since.isoformat(),),
            )
            row = cursor.fetchone()
            total = row["total_sent"] or 0
            delivered = row["delivered"] or 0
            return {
                "total_sent": total,
                "delivered": delivered,
                "delivery_rate": round(delivered / total * 100, 2) if total > 0 else 0.0,
                "with_image": row["with_image"] or 0,
                "fallback_images": row["fallback_images"] or 0,
            }
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта delivery stats: {e}")
            return {}

    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Статистика ошибок за последние N часов."""
        since = datetime.now() - timedelta(hours=hours)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_errors,
                    SUM(CASE WHEN error_type = 'FLOOD_WAIT' THEN 1 ELSE 0 END) as flood_wait_count,
                    SUM(CASE WHEN error_type = 'RetryAfter' THEN 1 ELSE 0 END) as retry_after_count,
                    SUM(CASE WHEN error_type = 'TelegramAPIError' THEN 1 ELSE 0 END) as api_errors,
                    SUM(CASE WHEN error_type = 'NetworkError' THEN 1 ELSE 0 END) as network_errors
                FROM delivery_errors
                WHERE occurred_at >= ?
            """,
                (since.isoformat(),),
            )
            row = cursor.fetchone()
            return {
                "total_errors": row["total_errors"] or 0,
                "flood_wait": row["flood_wait_count"] or 0,
                "retry_after": row["retry_after_count"] or 0,
                "api_errors": row["api_errors"] or 0,
                "network_errors": row["network_errors"] or 0,
            }
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта error stats: {e}")
            return {}

    def get_top_sources(self, days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """Топ источников по количеству публикаций за N дней."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    source_tag,
                    COUNT(*) as posts,
                    SUM(CASE WHEN delivered = 1 THEN 1 ELSE 0 END) as delivered,
                    AVG(score) as avg_score
                FROM message_stats
                WHERE sent_at >= ? AND source_tag IS NOT NULL AND source_tag != ''
                GROUP BY source_tag
                ORDER BY posts DESC
                LIMIT ?
            """,
                (since, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта top sources: {e}")
            return []

    def get_ctr_estimate(self, days: int = 7) -> float:
        """
        Оценка CTR по кликам на ссылки.
        Примечание: Telegram не предоставляет прямой API для подсчёта кликов.
        Возвращает 0.0 как placeholder — можно интегрировать с bit.ly или аналогом.
        """
        # TODO: интеграция с URL-shortener для реального CTR
        return 0.0

    # === AI Cost Tracking (P2-006) ===

    def record_ai_usage(
        self,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
        article_title: str = "",
    ) -> bool:
        """Записывает использование AI для отслеживания стоимости."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO ai_usage (provider, model, tokens_input, tokens_output, cost_usd, article_title, used_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    provider,
                    model,
                    tokens_input,
                    tokens_output,
                    cost_usd,
                    article_title,
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка записи ai_usage: {e}")
            return False

    def get_ai_cost(self, days: int = 1) -> Dict[str, Any]:
        """Возвращает суммарную стоимость AI-запросов за N дней."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as requests,
                    SUM(tokens_input) as total_input,
                    SUM(tokens_output) as total_output,
                    SUM(cost_usd) as total_cost
                FROM ai_usage
                WHERE used_at >= ?
            """,
                (since,),
            )
            row = cursor.fetchone()
            return {
                "requests": row["requests"] or 0,
                "tokens_input": row["total_input"] or 0,
                "tokens_output": row["total_output"] or 0,
                "cost_usd": round(row["total_cost"] or 0, 6),
            }
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта AI cost: {e}")
            return {"requests": 0, "tokens_input": 0, "tokens_output": 0, "cost_usd": 0.0}

    def get_ai_cost_by_provider(self, days: int = 7) -> List[Dict[str, Any]]:
        """Стоимость AI по провайдерам за N дней."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    provider,
                    model,
                    COUNT(*) as requests,
                    SUM(tokens_input) as total_input,
                    SUM(tokens_output) as total_output,
                    SUM(cost_usd) as total_cost
                FROM ai_usage
                WHERE used_at >= ?
                GROUP BY provider, model
                ORDER BY total_cost DESC
            """,
                (since,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта AI cost by provider: {e}")
            return []

    def check_ai_cost_alert(self, daily_budget: float = 10.0) -> tuple[bool, float]:
        """Проверяет, не превышен ли дневной бюджет. Возвращает (alert, spent)."""
        daily = self.get_ai_cost(days=1)
        spent = daily["cost_usd"]
        return spent >= daily_budget, spent

    def get_analytics_report(self) -> Dict[str, Any]:
        """Полный аналитический отчёт для команды /analytics."""
        delivery_24h = self.get_delivery_stats(hours=24)
        delivery_7d = self.get_delivery_stats(hours=24 * 7)
        errors_24h = self.get_error_stats(hours=24)
        errors_7d = self.get_error_stats(hours=24 * 7)
        top_sources = self.get_top_sources(days=7, limit=10)
        dau = self.get_dau(days=1)
        mau = self.get_mau()

        return {
            "period": "Последние 24ч / 7д",
            "dau": dau,
            "mau": mau,
            "delivery_24h": delivery_24h,
            "delivery_7d": delivery_7d,
            "errors_24h": errors_24h,
            "errors_7d": errors_7d,
            "top_sources": top_sources,
            "ctr_estimate": self.get_ctr_estimate(days=7),
        }

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с analytics закрыто")


# Глобальный экземпляр
analytics_manager = AnalyticsManager()
