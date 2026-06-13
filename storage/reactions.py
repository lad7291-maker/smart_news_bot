"""
Модуль системы пользовательских реакций.
P1-001: Система пользовательских реакций (👍/👎).

Таблицы:
- user_reactions: реакции пользователей на посты
- message_article_map: связь message_id → article_link для callback-обработки
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.db_maintenance import enable_wal_mode
from utils.logger import logger


class ReactionsManager:
    """Менеджер реакций пользователей: 👍 / 👎 / 💾."""

    # Веса реакций для влияния на score
    REACTION_WEIGHTS = {
        "like": 0.5,
        "dislike": -0.3,
        "save": 0.2,
    }

    def __init__(self, db_path: str = "storage/news_cache.db"):
        Path(db_path).parent.mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        enable_wal_mode(self.conn)
        self._init_database()
        logger.info(f"ReactionsManager инициализирован: {db_path}")

    def _init_database(self):
        cursor = self.conn.cursor()

        # --- Реакции пользователей ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                article_link TEXT NOT NULL,
                reaction_type TEXT NOT NULL CHECK(reaction_type IN ('like', 'dislike', 'save')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, user_id, reaction_type)
            )
        """
        )

        # --- Связь message_id → article_link ---
        # Нужна потому что callback приходит только с message_id,
        # а article_link нужен для аналитики
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_article_map (
                message_id INTEGER PRIMARY KEY,
                article_link TEXT NOT NULL,
                article_title TEXT,
                source_tag TEXT,
                score INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- Индексы ---
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reactions_article ON user_reactions(article_link)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reactions_type ON user_reactions(reaction_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reactions_created ON user_reactions(created_at)"
        )

        self.conn.commit()

    # === Запись данных ===

    def map_message_to_article(
        self,
        message_id: int,
        article_link: str,
        article_title: str = "",
        source_tag: str = "",
        score: int = 0,
    ) -> bool:
        """Сохраняет связь message_id → article_link при отправке поста."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO message_article_map
                (message_id, article_link, article_title, source_tag, score, sent_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    message_id,
                    article_link,
                    article_title,
                    source_tag,
                    score,
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка сохранения message_article_map: {e}")
            return False

    def add_reaction(self, message_id: int, user_id: str, reaction_type: str) -> Dict[str, Any]:
        """
        Добавляет реакцию пользователя.
        Если реакция уже есть — удаляет (toggle).
        Возвращает статистику по сообщению.
        """
        if reaction_type not in ("like", "dislike", "save"):
            return {"error": "Invalid reaction type"}

        try:
            cursor = self.conn.cursor()

            # Проверяем, есть ли уже такая реакция
            cursor.execute(
                """
                SELECT 1 FROM user_reactions
                WHERE message_id = ? AND user_id = ? AND reaction_type = ?
            """,
                (message_id, user_id, reaction_type),
            )
            exists = cursor.fetchone() is not None

            if exists:
                # Удаляем (toggle off)
                cursor.execute(
                    """
                    DELETE FROM user_reactions
                    WHERE message_id = ? AND user_id = ? AND reaction_type = ?
                """,
                    (message_id, user_id, reaction_type),
                )
                action = "removed"
            else:
                # Удаляем противоположную реакцию (like ↔ dislike)
                if reaction_type in ("like", "dislike"):
                    opposite = "dislike" if reaction_type == "like" else "like"
                    cursor.execute(
                        """
                        DELETE FROM user_reactions
                        WHERE message_id = ? AND user_id = ? AND reaction_type = ?
                    """,
                        (message_id, user_id, opposite),
                    )

                # Добавляем новую
                cursor.execute(
                    """
                    INSERT INTO user_reactions (message_id, user_id, article_link, reaction_type)
                    VALUES (?, ?, ?, ?)
                """,
                    (message_id, user_id, self._get_article_link(message_id) or "", reaction_type),
                )
                action = "added"

            self.conn.commit()
            stats = self.get_message_reactions(message_id)
            stats["action"] = action
            stats["reaction_type"] = reaction_type
            return stats

        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления реакции: {e}")
            return {"error": str(e)}

    def _get_article_link(self, message_id: int) -> Optional[str]:
        """Возвращает article_link по message_id."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT article_link FROM message_article_map WHERE message_id = ?",
                (message_id,),
            )
            row = cursor.fetchone()
            return row["article_link"] if row else None
        except sqlite3.Error:
            return None

    def get_message_reactions(self, message_id: int) -> Dict[str, Any]:
        """Возвращает статистику реакций для конкретного сообщения."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    reaction_type,
                    COUNT(*) as count
                FROM user_reactions
                WHERE message_id = ?
                GROUP BY reaction_type
            """,
                (message_id,),
            )
            rows = cursor.fetchall()
            stats = {"like": 0, "dislike": 0, "save": 0}
            for row in rows:
                stats[row["reaction_type"]] = row["count"]
            return stats
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения реакций: {e}")
            return {"like": 0, "dislike": 0, "save": 0}

    def get_article_score_boost(self, article_link: str) -> float:
        """
        Возвращает суммарный буст score для статьи на основе реакций.
        Используется в detect_score для влияния на ранжирование.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT reaction_type, COUNT(*) as count
                FROM user_reactions
                WHERE article_link = ?
                GROUP BY reaction_type
            """,
                (article_link,),
            )
            total = 0.0
            for row in cursor.fetchall():
                weight = self.REACTION_WEIGHTS.get(row["reaction_type"], 0)
                total += weight * row["count"]
            return total
        except sqlite3.Error as e:
            logger.error(f"Ошибка расчёта score boost: {e}")
            return 0.0

    def get_top_articles(self, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """Возвращает топ-N статей за N дней по реакциям."""
        since = datetime.now() - timedelta(days=days)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    m.article_link,
                    m.article_title,
                    m.source_tag,
                    m.score,
                    SUM(CASE WHEN r.reaction_type = 'like' THEN 1 ELSE 0 END) as likes,
                    SUM(CASE WHEN r.reaction_type = 'dislike' THEN 1 ELSE 0 END) as dislikes,
                    SUM(CASE WHEN r.reaction_type = 'save' THEN 1 ELSE 0 END) as saves,
                    COUNT(r.id) as total_reactions
                FROM message_article_map m
                LEFT JOIN user_reactions r ON m.article_link = r.article_link
                WHERE m.sent_at >= ?
                GROUP BY m.article_link
                HAVING total_reactions > 0
                ORDER BY (likes * 1.0 - dislikes * 0.6 + saves * 0.3) DESC
                LIMIT ?
            """,
                (since.isoformat(), limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения топа: {e}")
            return []

    def get_user_reaction_summary(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Сводка реакций конкретного пользователя."""
        since = datetime.now() - timedelta(days=days)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT
                    reaction_type,
                    COUNT(*) as count
                FROM user_reactions
                WHERE user_id = ? AND created_at >= ?
                GROUP BY reaction_type
            """,
                (user_id, since.isoformat()),
            )
            stats = {"like": 0, "dislike": 0, "save": 0, "total": 0}
            for row in cursor.fetchall():
                stats[row["reaction_type"]] = row["count"]
                stats["total"] += row["count"]
            return stats
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения сводки пользователя: {e}")
            return {"like": 0, "dislike": 0, "save": 0, "total": 0}

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с ReactionsManager закрыто")


# Глобальный экземпляр
reactions_manager = ReactionsManager()
