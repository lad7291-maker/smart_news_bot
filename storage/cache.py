import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from config import config
from utils.logger import logger


class CacheManager:
    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_database()
        logger.info(f"Кэш-менеджер инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_hash TEXT UNIQUE NOT NULL,
                original_link TEXT NOT NULL,
                source_type TEXT,
                source_tag TEXT,
                title TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                last_attempt TIMESTAMP,
                status TEXT DEFAULT 'new'
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        # FEAT-018: Персонализация — предпочтения пользователей/каналов
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                chat_id TEXT PRIMARY KEY,
                preferred_topics TEXT DEFAULT '[]',
                blocked_topics TEXT DEFAULT '[]',
                source_weights TEXT DEFAULT '{}',
                min_score INTEGER DEFAULT 1,
                quiet_hours_start INTEGER DEFAULT 23,
                quiet_hours_end INTEGER DEFAULT 7,
                max_posts_per_hour INTEGER DEFAULT 8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        # FEAT-022: Состояние health-check алертов (переживает перезапуск)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS health_alerts (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                alert_sent INTEGER DEFAULT 0,
                last_alert_time TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO health_alerts (id, alert_sent, last_alert_time)
            VALUES (1, 0, NULL)
        """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_link_hash ON processed_links(link_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON processed_links(status)")
        # Image dedup table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS used_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                image_url TEXT NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_url_hash ON used_images(url_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_used_at ON used_images(used_at)")
        self.conn.commit()

    def _generate_hash(self, link: str) -> str:
        return hashlib.md5(link.encode("utf-8")).hexdigest()

    def is_processed(self, link: str) -> bool:
        link_hash = self._generate_hash(link)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_links WHERE link_hash = ? AND status = 'processed'",
                (link_hash,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке ссылки: {e}")
            return False

    def mark_processing(
        self, link: str, source_type: str = "unknown", source_tag: str = "unknown", title: str = ""
    ) -> bool:
        link_hash = self._generate_hash(link)
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, attempts FROM processed_links WHERE link_hash = ?", (link_hash,)
            )
            existing = cursor.fetchone()
            if existing:
                new_attempts = existing["attempts"] + 1
                cursor.execute(
                    """
                    UPDATE processed_links
                    SET attempts = ?, last_attempt = ?, status = 'processing'
                    WHERE id = ?
                """,
                    (new_attempts, now, existing["id"]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO processed_links
                    (link_hash, original_link, source_type, source_tag, title,
                     processed_at, last_attempt, status, attempts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', 1)
                """,
                    (link_hash, link, source_type, source_tag, title, now, now),
                )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при пометке processing: {e}")
            return False

    def mark_processed(self, link: str, success: bool = True) -> bool:
        link_hash = self._generate_hash(link)
        status = "processed" if success else "failed"
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            if success:
                cursor.execute(
                    """
                    UPDATE processed_links
                    SET status = ?, last_attempt = ?, published_at = ?
                    WHERE link_hash = ?
                """,
                    (status, now, now, link_hash),
                )
            else:
                cursor.execute(
                    """
                    UPDATE processed_links
                    SET status = ?, last_attempt = ?
                    WHERE link_hash = ?
                """,
                    (status, now, link_hash),
                )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при пометке {status}: {e}")
            return False

    def get_processing_stats(self) -> Dict[str, Any]:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'processed' THEN 1 ELSE 0 END) as processed,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new
                FROM processed_links
            """
            )
            return dict(cursor.fetchone())
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {}

    def get_published_since(self, since: datetime) -> list:
        """Возвращает список опубликованных записей с published_at >= since."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT title, source_tag, score, published_at
                FROM processed_links
                WHERE status = 'processed' AND published_at >= ?
                ORDER BY published_at DESC
            """,
                (since.isoformat(),),
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении истории публикаций: {e}")
            return []

    def is_title_processed(self, title: str, hours: int = 24) -> bool:
        """
        Проверяет, была ли уже опубликована новость с ПОХОЖИМ заголовком.
        Используется для отлова дублей с разных источников (разные URL, одинаковый контент).
        """
        if not title or len(title) < 10:
            return False

        # Нормализуем заголовок для сравнения
        normalized = self._normalize_title(title)
        if not normalized:
            return False

        since = datetime.now() - timedelta(hours=hours)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT title FROM processed_links
                WHERE status = 'processed' AND published_at >= ?
            """,
                (since.isoformat(),),
            )

            for row in cursor.fetchall():
                existing_title = row["title"] or ""
                existing_normalized = self._normalize_title(existing_title)
                if not existing_normalized:
                    continue

                # Простое сравнение: если нормализованные заголовки совпадают на 85%+
                from difflib import SequenceMatcher

                sim = SequenceMatcher(None, normalized, existing_normalized).ratio()
                if sim >= 0.85:
                    logger.info(
                        f"🔄 Дубль по заголовку (sim={sim:.2f}): '{title[:60]}...' → похож на '{existing_title[:60]}...'"
                    )
                    return True

            return False
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке заголовка: {e}")
            return False

    def is_image_used(self, image_url: str, hours: int = 24) -> bool:
        """Проверяет, использовалось ли изображение за последние N часов."""
        if not image_url:
            return False
        url_hash = self._generate_hash(image_url)
        since = datetime.now() - timedelta(hours=hours)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM used_images WHERE url_hash = ? AND used_at >= ?",
                (url_hash, since.isoformat()),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке изображения: {e}")
            return False

    def mark_image_used(self, image_url: str) -> bool:
        """Отмечает изображение как использованное."""
        if not image_url:
            return False
        url_hash = self._generate_hash(image_url)
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO used_images (url_hash, image_url, used_at)
                VALUES (?, ?, ?)
            """,
                (url_hash, image_url, now),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при пометке изображения: {e}")
            return False

    def _normalize_title(self, title: str) -> str:
        """Нормализует заголовок для сравнения."""
        import re

        text = title.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\d+[\.,]?\d*", "", text)
        # Убираем стоп-слова
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "этот",
            "эта",
            "это",
            "как",
            "для",
            "что",
            "где",
            "когда",
            "кто",
            "из",
            "на",
            "в",
            "и",
            "или",
            "но",
            "за",
            "по",
            "от",
            "до",
            "со",
            "при",
            "об",
            "про",
            "под",
            "над",
            "перед",
            "после",
            "между",
            "через",
            "без",
            "около",
            "против",
            "вместо",
            "новый",
            "новое",
            "новая",
            "новые",
            "последний",
            "последнее",
            "последняя",
            "today",
            "yesterday",
            "now",
            "just",
            "new",
            "latest",
            "breaking",
            "update",
            "сегодня",
            "вчера",
            "сейчас",
            "только",
            "последние",
            "экстренно",
            "срочно",
            "said",
            "says",
            "say",
            "will",
            "about",
            "into",
            "than",
            "only",
            "other",
        }
        words = [w for w in text.split() if w and w not in stop_words and len(w) > 2]
        return " ".join(words)

    def get_last_published_by_topic(
        self, topic_keyword: str, since: datetime
    ) -> Optional[datetime]:
        """Возвращает время последней публикации, где title содержит topic_keyword."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT published_at FROM processed_links
                WHERE status = 'processed' AND title LIKE ? AND published_at >= ?
                ORDER BY published_at DESC LIMIT 1
            """,
                (f"%{topic_keyword}%", since.isoformat()),
            )
            row = cursor.fetchone()
            if row and row["published_at"]:
                return datetime.fromisoformat(row["published_at"])
            return None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при поиске по теме: {e}")
            return None

    # === FEAT-018: Методы персонализации ===

    def get_user_prefs(self, chat_id: str) -> Dict[str, Any]:
        """Возвращает предпочтения пользователя/канала."""
        import json

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM user_preferences WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "chat_id": row["chat_id"],
                    "preferred_topics": json.loads(row["preferred_topics"]),
                    "blocked_topics": json.loads(row["blocked_topics"]),
                    "source_weights": json.loads(row["source_weights"]),
                    "min_score": row["min_score"],
                    "quiet_hours_start": row["quiet_hours_start"],
                    "quiet_hours_end": row["quiet_hours_end"],
                    "max_posts_per_hour": row["max_posts_per_hour"],
                }
            # Возвращаем дефолтные настройки
            return {
                "chat_id": chat_id,
                "preferred_topics": [],
                "blocked_topics": [],
                "source_weights": {},
                "min_score": 1,
                "quiet_hours_start": 23,
                "quiet_hours_end": 7,
                "max_posts_per_hour": 8,
            }
        except sqlite3.Error as e:
            logger.error(f"Ошибка при чтении предпочтений: {e}")
            return {
                "chat_id": chat_id,
                "preferred_topics": [],
                "blocked_topics": [],
                "source_weights": {},
                "min_score": 1,
                "quiet_hours_start": 23,
                "quiet_hours_end": 7,
                "max_posts_per_hour": 8,
            }

    def set_user_prefs(self, chat_id: str, **kwargs) -> bool:
        """Обновляет предпочтения пользователя/канала."""
        import json

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM user_preferences WHERE chat_id = ?", (chat_id,))
            exists = cursor.fetchone() is not None

            fields = []
            values = []
            for key, value in kwargs.items():
                if key in (
                    "preferred_topics",
                    "blocked_topics",
                    "source_weights",
                ):
                    value = json.dumps(value)
                fields.append(f"{key} = ?")
                values.append(value)

            if not fields:
                return True

            values.append(chat_id)
            if exists:
                sql = f"UPDATE user_preferences SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?"
            else:
                sql = f"INSERT INTO user_preferences ({', '.join(kwargs.keys())}, chat_id) VALUES ({', '.join(['?'] * len(kwargs))}, ?)"

            cursor.execute(sql, values)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при сохранении предпочтений: {e}")
            return False

    # === FEAT-022: Методы для health-check алертов (переживают перезапуск) ===

    def get_health_alert_state(self) -> Dict[str, Any]:
        """Возвращает состояние алертов из БД."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT alert_sent, last_alert_time FROM health_alerts WHERE id = 1")
            row = cursor.fetchone()
            if row:
                from datetime import datetime

                last_time = row["last_alert_time"]
                if last_time:
                    last_time = datetime.fromisoformat(last_time)
                return {
                    "alert_sent": bool(row["alert_sent"]),
                    "last_alert_time": last_time,
                }
            return {"alert_sent": False, "last_alert_time": None}
        except sqlite3.Error as e:
            logger.error(f"Ошибка при чтении состояния алертов: {e}")
            return {"alert_sent": False, "last_alert_time": None}

    def set_health_alert_state(self, alert_sent: bool, last_alert_time: Optional[datetime]) -> bool:
        """Сохраняет состояние алертов в БД."""
        try:
            cursor = self.conn.cursor()
            time_str = last_alert_time.isoformat() if last_alert_time else None
            cursor.execute(
                """
                UPDATE health_alerts
                SET alert_sent = ?, last_alert_time = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """,
                (1 if alert_sent else 0, time_str),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при сохранении состояния алертов: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с кэшем закрыто")


cache_manager = CacheManager()
