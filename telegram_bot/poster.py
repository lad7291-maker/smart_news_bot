"""
Модуль для отправки новостей в Telegram-канал.
Поддерживает отправку с изображением (image_url) или текстом.
"""
import asyncio
from typing import List, Dict, Any
from aiogram.types import URLInputFile
from aiogram.exceptions import TelegramAPIError
from .core import bot
from .formatter import format_news_post
from config import config
from utils.logger import logger


def _truncate_caption(text: str, max_len: int = 1024) -> str:
    """Обрезает текст до лимита caption Telegram (1024 символа)."""
    if len(text) <= max_len:
        return text
    # Оставляем запас на многоточие
    truncated = text[: max_len - 3].rsplit(" ", 1)[0]
    return truncated + "…"


async def send_news_to_channel(article: Dict[str, Any]) -> bool:
    """
    Отправляет одну новость в канал.
    Если в article есть 'image_url' — отправляет как фото с caption.
    Если фото нет или оно нерелевантное — отправляет текст с превью ссылки.
    """
    try:
        message_text = format_news_post(article)
        image_url = article.get("image_url")
        is_fallback = article.get("image_is_fallback", False)

        if image_url and not is_fallback:
            # Отправляем с реальным фото
            caption = _truncate_caption(message_text)
            photo = URLInputFile(image_url)
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                photo=photo,
                caption=caption,
            )
            logger.info(f"✅ Отправлено с фото: {article['title'][:50]}...")
        elif image_url and is_fallback:
            # Fallback-изображение (флаг/логотип) — отправляем как фото
            caption = _truncate_caption(message_text)
            photo = URLInputFile(image_url)
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                photo=photo,
                caption=caption,
            )
            logger.info(f"✅ Отправлено с fallback-фото ({article.get('image_source', 'unknown')}): {article['title'][:50]}...")
        else:
            # Без фото — текст с превью ссылки
            await bot.send_message(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                text=message_text,
                disable_web_page_preview=False,
            )
            logger.info(f"✅ Отправлено (текст): {article['title'][:50]}...")
        return True
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка Telegram API: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка при отправке: {e}", exc_info=True)
        return False

async def send_multiple_news(articles: List[Dict[str, Any]], 
                            max_posts: int = 3, 
                            delay: float = 2.0) -> int:
    """
    Отправляет несколько новостей с паузой.
    """
    sent_count = 0
    for article in articles[:max_posts]:
        if await send_news_to_channel(article):
            sent_count += 1
            await asyncio.sleep(delay)
    return sent_count