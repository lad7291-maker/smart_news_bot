# -*- coding: utf-8 -*-
"""
SmartNewsAI Poster — отправка постов в Telegram
Priority: photo → video → text fallback
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict

from telegram_bot.formatter import format_news_post

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# Импорты с fallback
# ──────────────────────────────────────────
try:
    from utils.image_search import find_news_image
except ImportError:
    find_news_image = None

try:
    from utils.image_processor import process_image_for_telegram
except ImportError:
    process_image_for_telegram = None

try:
    from parsers.image_extractor import _is_og_reliable_domain
except ImportError:

    def _is_og_reliable_domain(url):
        return False


def _truncate_caption(text: str, max_len: int = 1024) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - 3].rsplit(" ", 1)[0]
    return truncated + "…"


async def send_news_to_channel(
    bot,
    channel_id: str,
    news: Dict[str, Any],
) -> bool:
    """
    Отправляет новостной пост в Telegram-канал.
    Priority: photo → video → text fallback
    """
    message_text = format_news_post(news)

    # 1. Пробуем фото (приоритет: RSS/OG/HTML → Stock → Скриншот → SearXNG → Fallback)
    if find_news_image and process_image_for_telegram:
        try:
            image_url = await find_news_image(news)
            if image_url:
                # Проверяем, является ли URL скриншотом (это URL статьи, а не изображения)
                from utils.screenshot_generator import (
                    _is_screenshot_friendly,
                    process_screenshot_for_telegram,
                )

                is_screenshot = (
                    _is_screenshot_friendly(image_url)
                    and not any(
                        image_url.lower().endswith(ext)
                        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
                    )
                    and "image" not in image_url.lower()
                )

                if image_url.startswith("/tmp/") or image_url.startswith("/"):
                    # Это локальный файл (скриншот твита)
                    from aiogram.types import FSInputFile

                    photo_file = FSInputFile(image_url)
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=photo_file,
                        caption=_truncate_caption(message_text),
                        parse_mode="HTML",
                    )
                    return True
                elif is_screenshot:
                    # Это скриншот — обрабатываем через screenshot pipeline
                    image_data = await process_screenshot_for_telegram(
                        image_url, article_title=news.get("title", ""), timeout=30.0
                    )
                else:
                    # Обычное изображение — проверяем, доверенный ли домен
                    trusted = _is_og_reliable_domain(image_url) if _is_og_reliable_domain else False
                    processed = await process_image_for_telegram(
                        image_url,
                        article_title=news.get("title", ""),
                        source=news.get("source", ""),
                        trusted_domain=trusted,
                    )
                    image_data = processed if isinstance(processed, bytes) else None

                if image_data:
                    caption = _truncate_caption(message_text)
                    # aiogram 3.x expects FSInputFile for bytes
                    import tempfile

                    from aiogram.types import FSInputFile

                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        tmp.write(image_data)
                        tmp_path = tmp.name
                    photo_file = FSInputFile(tmp_path, filename="image.jpg")
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=photo_file,
                        caption=caption,
                        parse_mode="HTML",
                    )
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    # Mark image as used for dedup
                    try:
                        from storage.cache import cache_manager

                        cache_manager.mark_image_used(image_url)
                    except Exception:
                        pass
                    return True
        except Exception as e:
            logger.warning(f"Photo send failed: {e}")
            pass

    # 2. Пробуем branded video
    try:
        video_path = Path("assets/branded_video.mp4")
        if video_path.exists():
            with open(video_path, "rb") as f:
                await bot.send_video(
                    chat_id=channel_id,
                    video=f,
                    caption=_truncate_caption(message_text),
                    parse_mode="HTML",
                )
                return True
    except Exception:
        pass

    # 3. Текстовый fallback
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=message_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.error(f"send_news_to_channel failed: {e}")
        return False


async def send_multiple_news(
    bot,
    channel_id: str,
    articles,
    max_posts: int = 3,
    delay: int = 3,
):
    """Отправляет несколько новостей в канал с задержкой между постами."""
    sent = 0
    for article in articles[:max_posts]:
        try:
            success = await send_news_to_channel(bot, channel_id, article)
            if success:
                sent += 1
            if delay and len(articles[:max_posts]) > 1:
                await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"send_multiple_news: {e}")
    return sent
