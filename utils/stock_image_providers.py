"""
Поиск изображений через бесплатные стоки: Unsplash, Pexels, Pixabay.

Лицензии:
- Unsplash: бесплатно для коммерческого и некоммерческого использования,
  желательно указать автора. Нельзя продавать без значимых изменений.
- Pexels: бесплатно, коммерческое использование разрешено,
  нельзя продавать как есть, желательно указать автора.
- Pixabay: CC0 — полностью свободно, без атрибуции.

API Limits (бесплатный tier):
- Unsplash: 50 запросов/час
- Pexels: 200 запросов/час
- Pixabay: 100 запросов/час
"""

import asyncio
import io
import logging
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

from config import config
from utils.logger import logger

logger = logging.getLogger(__name__)

# API Keys (должны быть в config.py или .env)
UNSPLASH_ACCESS_KEY = getattr(config, "UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY = getattr(config, "PEXELS_API_KEY", "")
PIXABAY_API_KEY = getattr(config, "PIXABAY_API_KEY", "")

# Endpoints
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
PEXELS_API_URL = "https://api.pexels.com/v1/search"
PIXABAY_API_URL = "https://pixabay.com/api/"

# Таймауты
REQUEST_TIMEOUT = 8.0


async def _check_image_valid(url: str) -> bool:
    """Проверяет, что изображение не битое и не пустое."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": config.USER_AGENT})
            if resp.status_code != 200:
                return False
            # Проверяем, что это реальное изображение
            content = resp.content
            if len(content) < 2048:  # Меньше 2KB — скорее всего битое/пустое
                return False
            # Проверяем через PIL
            img = Image.open(io.BytesIO(content))
            img.load()
            # Проверяем на полностью черное/белое изображение
            if img.mode in ("RGB", "RGBA"):
                # Convert to grayscale for analysis
                gray = img.convert("L")
                pixels = list(gray.getdata())
                avg_brightness = sum(pixels) / len(pixels)
                # Если средняя яркость < 10 (почти черное) или > 245 (почти белое)
                if avg_brightness < 10 or avg_brightness > 245:
                    logger.debug(f"Image too dark/bright: {url[:60]}")
                    return False
            return True
    except Exception as e:
        logger.debug(f"Image validation failed: {url[:60]}: {e}")
        return False


async def search_unsplash(query: str, max_results: int = 5) -> List[str]:
    """Поиск через Unsplash API."""
    if not UNSPLASH_ACCESS_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(
                UNSPLASH_API_URL,
                params={
                    "query": query,
                    "per_page": max_results,
                    "orientation": "landscape",  # Для Telegram постов 16:9
                },
                headers={
                    "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
                    "User-Agent": config.USER_AGENT,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            urls = []
            for photo in data.get("results", []):
                # Используем regular size (1080px) для баланса качества/скорости
                url = photo.get("urls", {}).get("regular")
                if url:
                    urls.append(url)

            logger.info(f"Unsplash: {len(urls)} results for '{query[:40]}'")
            return urls

    except Exception as e:
        logger.debug(f"Unsplash search failed: {e}")
        return []


async def search_pexels(query: str, max_results: int = 5) -> List[str]:
    """Поиск через Pexels API."""
    if not PEXELS_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(
                PEXELS_API_URL,
                params={
                    "query": query,
                    "per_page": max_results,
                    "orientation": "landscape",
                },
                headers={
                    "Authorization": PEXELS_API_KEY,
                    "User-Agent": config.USER_AGENT,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            urls = []
            for photo in data.get("photos", []):
                # large2x — хорошее качество
                url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
                if url:
                    urls.append(url)

            logger.info(f"Pexels: {len(urls)} results for '{query[:40]}'")
            return urls

    except Exception as e:
        logger.debug(f"Pexels search failed: {e}")
        return []


async def search_pixabay(query: str, max_results: int = 5) -> List[str]:
    """Поиск через Pixabay API (CC0)."""
    if not PIXABAY_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(
                PIXABAY_API_URL,
                params={
                    "q": query,
                    "per_page": max_results,
                    "orientation": "horizontal",
                    "key": PIXABAY_API_KEY,
                    "safesearch": "true",  # Важно для новостного бота
                    "image_type": "photo",
                },
                headers={"User-Agent": config.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()

            urls = []
            for photo in data.get("hits", []):
                # webformatURL — 640px, largeImageURL — полный размер
                url = photo.get("largeImageURL") or photo.get("webformatURL")
                if url:
                    urls.append(url)

            logger.info(f"Pixabay: {len(urls)} results for '{query[:40]}'")
            return urls

    except Exception as e:
        logger.debug(f"Pixabay search failed: {e}")
        return []


async def search_all_stocks(query: str, max_per_source: int = 3) -> List[str]:
    """Поиск через все доступные стоки одновременно."""
    tasks = [
        search_unsplash(query, max_per_source),
        search_pexels(query, max_per_source),
        search_pixabay(query, max_per_source),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_urls = []
    for result in results:
        if isinstance(result, list):
            all_urls.extend(result)

    # Удаляем дубликаты, сохраняя порядок
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    logger.info(f"Stock search total: {len(unique_urls)} unique for '{query[:40]}'")
    return unique_urls


async def find_best_stock_image(title: str, summary: str = "") -> Optional[str]:
    """
    Ищет лучшее изображение через стоки.

    Стратегия:
    1. Пробуем поиск по заголовку
    2. Если нет результатов — поиск по ключевым словам из summary
    3. Валидируем изображения (не битые, не пустые)
    4. Возвращаем первое валидное
    """
    from utils.text_utils import extract_keywords

    # Формируем запросы
    queries = [title]

    # Добавляем ключевые слова
    keywords = extract_keywords(f"{title} {summary}", max_keywords=5)
    if keywords:
        queries.append(" ".join(keywords))

    # Пробуем каждый запрос
    for query in queries:
        if not query or len(query) < 3:
            continue

        urls = await search_all_stocks(query, max_per_source=3)

        # Валидируем каждое изображение
        for url in urls[:5]:  # Проверяем первые 5
            if await _check_image_valid(url):
                logger.info(f"✅ Valid stock image found: {url[:60]}...")
                return url
            else:
                logger.debug(f"❌ Invalid/broken image: {url[:60]}...")

    logger.info(f"🚫 No valid stock images found for: {title[:60]}...")
    return None
