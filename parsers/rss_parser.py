"""
Модуль для парсинга RSS-лент.
Использует feedparser для получения новостей из RSS-источников.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import feedparser

from config import config

logger = logging.getLogger(__name__)


class RSSParser:
    """Парсер RSS-лент с фильтрацией по времени и обработкой ошибок."""

    def __init__(self, hours_limit: int = 72):
        """
        Args:
            hours_limit: Возвращать новости не старше этого количества часов
        """
        self.hours_limit = hours_limit

    def parse_feed(self, feed_url: str, source_tag: str) -> List[Dict[str, Any]]:
        """
        Парсит одну RSS-ленту и возвращает список свежих новостей.

        Args:
            feed_url: URL RSS-ленты
            source_tag: Тег источника (например, 'AI', 'Crypto')

        Returns:
            Список словарей с данными новостей
        """
        articles = []
        try:
            logger.debug(f"Загрузка RSS: {feed_url}")
            feed = feedparser.parse(feed_url)

            if feed.get("bozo_exception", False):
                logger.warning(f"Проблема при парсинге {feed_url}: {feed.bozo_exception}")

            for entry in feed.entries[:10]:  # Берём не более 10 записей
                # Извлекаем и нормализуем дату публикации
                published_time = self._extract_published_date(entry)

                # Пропускаем старые новости
                if datetime.now() - published_time > timedelta(hours=self.hours_limit):
                    continue

                article = self._build_article(entry, source_tag, published_time)
                articles.append(article)

            logger.info(f"RSS {source_tag}: получено {len(articles)} свежих новостей")
        except Exception as e:
            logger.error(f"Ошибка при парсинге RSS {feed_url}: {e}", exc_info=True)

        return articles

    def _extract_published_date(self, entry: Any) -> datetime:
        """Извлекает дату публикации из записи RSS."""
        # Пробуем разные поля, где может быть дата
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6])
        elif hasattr(entry, "created_parsed") and entry.created_parsed:
            return datetime(*entry.created_parsed[:6])
        else:
            # Если даты нет, считаем текущее время (новость только что добавлена)
            return datetime.now()

    def _build_article(
        self, entry: Any, source_tag: str, published_time: datetime
    ) -> Dict[str, Any]:
        """Формирует структурированную запись о новости."""
        return {
            "title": self._clean_text(entry.get("title", "Без заголовка")),
            "link": entry.get("link", ""),
            "summary": self._clean_text(entry.get("summary", entry.get("description", ""))),
            "source": source_tag,
            "published": published_time,
            "type": "rss",
            "source_url": entry.get("link", ""),  # для обратной совместимости
            "rss_entry": entry,  # Сохраняем raw entry для извлечения изображений
        }

    def _clean_text(self, text: str) -> str:
        """Очищает текст от лишних пробелов и HTML-тегов."""
        if not text:
            return ""
        # Убираем HTML-теги (простейшая очистка)
        import re

        text = re.sub(r"<[^>]+>", "", text)
        # Убираем лишние пробелы и переносы строк
        text = " ".join(text.split())
        return text[:500]  # Ограничиваем длину


# Для совместимости со старым кодом оставляем функцию-обёртку
def parse_rss_feed(feed_url: str, source_tag: str, hours_limit: int = 72) -> List[Dict[str, Any]]:
    """Функция-обёртка для обратной совместимости."""
    parser = RSSParser(hours_limit=hours_limit)
    return parser.parse_feed(feed_url, source_tag)


if __name__ == "__main__":
    # Простой тест при запуске файла напрямую
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import setup_logging

    setup_logging()

    test_sources = [
        {"url": "https://habr.com/ru/rss/hub/ai/?fl=ru", "tag": "AI"},
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "tag": "Crypto"},
    ]

    parser = RSSParser(hours_limit=168)  # последние 7 дней для теста
    for source in test_sources:
        news = parser.parse_feed(source["url"], source["tag"])
        print(f"\n🔹 {source['tag']}: {len(news)} новостей")
        for i, item in enumerate(news[:3], 1):
            print(f"   {i}. {item['title'][:80]}...")
