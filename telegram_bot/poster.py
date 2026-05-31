import asyncio
from typing import Any, Dict

from aiogram.exceptions import TelegramAPIError
from aiogram.types import URLInputFile

_NETWORK_ERRORS = [ConnectionError, TimeoutError, OSError]
try:
    from aiohttp import ClientConnectionError

    _NETWORK_ERRORS.append(ClientConnectionError)
except ImportError:
    pass
_NETWORK_ERRORS = tuple(_NETWORK_ERRORS)

from config import config
from utils.logger import logger

from .core import bot
from .formatter import format_news_post


def _truncate_caption(text: str, max_len: int = 1024) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - 3].rsplit(" ", 1)[0]
    return truncated + "…"


async def _send_with_retry(send_func, max_retries=3, base_delay=2):
    for attempt in range(max_retries):
        try:
            return await send_func()
        except _NETWORK_ERRORS as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"⚠️ Сеть Telegram недоступна (попытка {attempt+1}/{max_retries}), ждём {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"❌ Telegram недоступен после {max_retries} попыток: {e}")
                raise
        except TelegramAPIError:
            raise


async def send_news_to_channel(article: Dict[str, Any]) -> bool:
    try:
        message_text = format_news_post(article)
        image_url = article.get("image_url")
        is_fallback = article.get("image_is_fallback", False)

        if image_url:
            try:
                caption = _truncate_caption(message_text)
                photo = URLInputFile(image_url)
                await _send_with_retry(
                    lambda: bot.send_photo(
                        chat_id=config.TELEGRAM_CHANNEL_ID,
                        photo=photo,
                        caption=caption,
                    )
                )
                src = article.get("image_source", "unknown")
                if is_fallback:
                    logger.info(
                        f'✅ Отправлено с fallback-фото ({src}): {article["title"][:50]}...'
                    )
                else:
                    logger.info(f'✅ Отправлено с фото: {article["title"][:50]}...')
                return True
            except Exception as photo_err:
                logger.warning(
                    f'⚠️ Фото не загрузилось ({photo_err}), отправляем текстом: {article["title"][:50]}...'
                )
                await _send_with_retry(
                    lambda: bot.send_message(
                        chat_id=config.TELEGRAM_CHANNEL_ID,
                        text=message_text,
                        disable_web_page_preview=False,
                    )
                )
                logger.info(f'✅ Отправлено (текст, фото недоступно): {article["title"][:50]}...')
                return True
        else:
            await _send_with_retry(
                lambda: bot.send_message(
                    chat_id=config.TELEGRAM_CHANNEL_ID,
                    text=message_text,
                    disable_web_page_preview=False,
                )
            )
            logger.info(f'✅ Отправлено (текст): {article["title"][:50]}...')
            return True
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка Telegram API: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка при отправке: {e}", exc_info=True)
        return False


async def send_multiple_news(articles, max_posts=3, delay=3):
    """Отправляет несколько новостей в канал с задержкой между постами.

    Args:
        articles: список словарей с новостями
        max_posts: максимальное количество постов
        delay: задержка между постами в секундах

    Returns:
        int: количество успешно отправленных постов
    """
    sent = 0
    for article in articles[:max_posts]:
        try:
            success = await send_news_to_channel(article)
            if success:
                sent += 1
            if delay and len(articles[:max_posts]) > 1:
                await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке поста {sent+1}: {e}")
    return sent
