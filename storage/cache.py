import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
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
        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_hash ON processed_links(link_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON processed_links(status)')
        self.conn.commit()
    
    def _generate_hash(self, link: str) -> str:
        return hashlib.md5(link.encode('utf-8')).hexdigest()
    
    def is_processed(self, link: str) -> bool:
        link_hash = self._generate_hash(link)
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_links WHERE link_hash = ? AND status = 'processed'",
                (link_hash,)
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке ссылки: {e}")
            return False
    
    def mark_processing(self, link: str, source_type: str = "unknown",
                       source_tag: str = "unknown", title: str = "") -> bool:
        link_hash = self._generate_hash(link)
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, attempts FROM processed_links WHERE link_hash = ?",
                (link_hash,)
            )
            existing = cursor.fetchone()
            if existing:
                new_attempts = existing['attempts'] + 1
                cursor.execute('''
                    UPDATE processed_links 
                    SET attempts = ?, last_attempt = ?, status = 'processing'
                    WHERE id = ?
                ''', (new_attempts, now, existing['id']))
            else:
                cursor.execute('''
                    INSERT INTO processed_links 
                    (link_hash, original_link, source_type, source_tag, title, 
                     processed_at, last_attempt, status, attempts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', 1)
                ''', (link_hash, link, source_type, source_tag, title, now, now))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при пометке processing: {e}")
            return False
    
    def mark_processed(self, link: str, success: bool = True) -> bool:
        link_hash = self._generate_hash(link)
        status = 'processed' if success else 'failed'
        now = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            if success:
                cursor.execute('''
                    UPDATE processed_links 
                    SET status = ?, last_attempt = ?, published_at = ?
                    WHERE link_hash = ?
                ''', (status, now, now, link_hash))
            else:
                cursor.execute('''
                    UPDATE processed_links 
                    SET status = ?, last_attempt = ?
                    WHERE link_hash = ?
                ''', (status, now, link_hash))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при пометке {status}: {e}")
            return False
    
    def get_processing_stats(self) -> Dict[str, Any]:
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'processed' THEN 1 ELSE 0 END) as processed,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new
                FROM processed_links
            ''')
            return dict(cursor.fetchone())
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {}

    def get_published_since(self, since: datetime) -> list:
        """Возвращает список опубликованных записей с published_at >= since."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT title, source_tag, score, published_at
                FROM processed_links
                WHERE status = 'processed' AND published_at >= ?
                ORDER BY published_at DESC
            ''', (since.isoformat(),))
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
            cursor.execute('''
                SELECT title FROM processed_links 
                WHERE status = 'processed' AND published_at >= ?
            ''', (since.isoformat(),))
            
            for row in cursor.fetchall():
                existing_title = row['title'] or ""
                existing_normalized = self._normalize_title(existing_title)
                if not existing_normalized:
                    continue
                
                # Простое сравнение: если нормализованные заголовки совпадают на 85%+
                from difflib import SequenceMatcher
                sim = SequenceMatcher(None, normalized, existing_normalized).ratio()
                if sim >= 0.85:
                    logger.info(f"🔄 Дубль по заголовку (sim={sim:.2f}): '{title[:60]}...' → похож на '{existing_title[:60]}...'")
                    return True
            
            return False
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке заголовка: {e}")
            return False
    
    def _normalize_title(self, title: str) -> str:
        """Нормализует заголовок для сравнения."""
        import re
        text = title.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\d+[\.,]?\d*", "", text)
        # Убираем стоп-слова
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
            "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
            "этот", "эта", "это", "как", "для", "что", "где", "когда", "кто", "из", "на", "в", "и",
            "или", "но", "за", "по", "от", "до", "со", "при", "об", "про", "под", "над", "перед",
            "после", "между", "через", "без", "около", "против", "вместо",
            "новый", "новое", "новая", "новые", "последний", "последнее", "последняя",
            "today", "yesterday", "now", "just", "new", "latest", "breaking", "update",
            "сегодня", "вчера", "сейчас", "только", "последние", "экстренно", "срочно",
            "said", "says", "say", "will", "about", "into", "than", "only", "other",
        }
        words = [w for w in text.split() if w and w not in stop_words and len(w) > 2]
        return " ".join(words)

    def get_last_published_by_topic(self, topic_keyword: str, since: datetime) -> Optional[datetime]:
        """Возвращает время последней публикации, где title содержит topic_keyword."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT published_at FROM processed_links
                WHERE status = 'processed' AND title LIKE ? AND published_at >= ?
                ORDER BY published_at DESC LIMIT 1
            ''', (f'%{topic_keyword}%', since.isoformat()))
            row = cursor.fetchone()
            if row and row['published_at']:
                return datetime.fromisoformat(row['published_at'])
            return None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при поиске по теме: {e}")
            return None

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Соединение с кэшем закрыто")

cache_manager = CacheManager()