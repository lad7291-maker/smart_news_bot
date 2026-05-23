#!/usr/bin/env python3
"""
Главная точка входа: парсинг новостей и отправка в Telegram.
Финальная стабильная версия.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую папку в путь для импорта
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logging
from storage.cache import cache_manager
from parsers.rss_parser import RSSParser
from telegram_bot.poster import send_multiple_news
from config import config

logger = setup_logging()

async def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК SMART NEWS BOT")
    logger.info("=" * 60)

    # Инициализируем переменную бота для гарантированного закрытия
    bot_instance = None

    try:
        # 1. Парсинг новостей
        logger.info("📡 Шаг 1: Сбор новостей из RSS...")
        parser = RSSParser(hours_limit=72)
        all_news = []

        for source in config.RSS_SOURCES:
            try:
                news = parser.parse_feed(source['url'], source['tag'])
                # Фильтруем уже обработанные
                fresh_news = [n for n in news if not cache_manager.is_processed(n['link'])]
                all_news.extend(fresh_news)
            except Exception as e:
                logger.warning(f"Ошибка при парсинге {source['tag']}: {e}")
                continue

        # Сортируем по дате (свежие сверху)
        all_news.sort(key=lambda x: x['published'], reverse=True)
        logger.info(f"📊 Найдено свежих новостей: {len(all_news)}")

        if not all_news:
            logger.info("😴 Нет новых новостей для публикации")
            return 0

        # 2. Отправка в Telegram
        logger.info("📤 Шаг 2: Отправка в Telegram...")

        # Помечаем как обрабатываемые (первые 3)
        for article in all_news[:3]:
            cache_manager.mark_processing(
                article['link'],
                article['type'],
                article['source'],
                article['title']
            )

        # Отправляем посты
        sent = await send_multiple_news(all_news, max_posts=3, delay=3)
        logger.info(f"✅ Отправлено постов: {sent}")

        # Помечаем успешно отправленные
        for article in all_news[:sent]:
            cache_manager.mark_processed(article['link'], success=True)

    except KeyboardInterrupt:
        logger.info("🛑 Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        return 1
    finally:
        # --- Важное исправление: принудительно закрываем сессию бота ---
        try:
            from telegram_bot.core import bot
            bot_instance = bot
            if bot_instance and hasattr(bot_instance, 'session'):
                await bot_instance.session.close()
                logger.info("🔌 Сессия Telegram-бота закрыта")
        except Exception as e:
            logger.warning(f"Не удалось закрыть сессию бота: {e}")

        # Закрываем соединение с кэшем
        cache_manager.close()
        logger.info("📴 Все ресурсы освобождены")

    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except RuntimeError as e:
        # Ловим ошибки связанные с циклом событий
        print(f"Ошибка выполнения: {e}")
        sys.exit(1)