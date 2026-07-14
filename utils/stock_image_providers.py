# -*- coding: utf-8 -*-
"""
Поиск изображений через бесплатные стоки: Unsplash, Pexels, Pixabay.

Лицензии:
- Unsplash: бесплатно для коммерческого и некоммерческого использования,
  желательно указать автора. Нельзя продавать без значимых изменений.
- Pexels: бесплатно, коммерческое использование разрешено,
  нельзя продать как есть, желательно указать автора.
- Pixabay: CC0 — полностью свободно, без атрибуции.

API Limits (бесплатный tier):
- Unsplash: 50 запросов/час
- Pexels: 200 запросов/час
- Pixabay: 100 запросов/час
"""

import asyncio
import io
import logging
import re
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
            content = resp.content
            if len(content) < 2048:
                return False
            img = Image.open(io.BytesIO(content))
            img.load()
            if img.mode in ("RGB", "RGBA"):
                gray = img.convert("L")
                pixels = list(gray.getdata())
                avg_brightness = sum(pixels) / len(pixels)
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
                params={"query": query, "per_page": max_results, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}", "User-Agent": config.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
            urls = []
            for photo in data.get("results", []):
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
                params={"query": query, "per_page": max_results, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY, "User-Agent": config.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
            urls = []
            for photo in data.get("photos", []):
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
                params={"q": query, "per_page": max_results, "orientation": "horizontal", "key": PIXABAY_API_KEY, "safesearch": "true", "image_type": "photo"},
                headers={"User-Agent": config.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
            urls = []
            for photo in data.get("hits", []):
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
    tasks = [search_unsplash(query, max_per_source), search_pexels(query, max_per_source), search_pixabay(query, max_per_source)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_urls = []
    for result in results:
        if isinstance(result, list):
            all_urls.extend(result)
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    logger.info(f"Stock search total: {len(unique_urls)} unique for '{query[:40]}'")
    return unique_urls


def _clean_title_for_search(title: str) -> str:
    """Убирает даты, дни недели, числа — оставляет только сущности."""
    months = r"январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]"
    days = r"понедельник|вторник|сред[аы]|четверг|пятниц[аы]|суббот[аы]|воскресень[ея]"
    title = re.sub(r"\b\d{1,2}\s*" + months + r"\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b" + months + r"\s*\d{1,4}\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b" + days + r"\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b20\d{2}\b", "", title)
    title = re.sub(r"\b\d{1,2}[:\.]\d{2}\b", "", title)
    title = re.sub(r"\b\d+\b", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return " ".join(title.split())


def _detect_topic_context(title: str, summary: str = "") -> str:
    """Определяет тематический контекст для улучшения поиска."""
    text = f"{title} {summary}".lower()
    contexts = {
        "politics": ["санкци", "политик", "парламент", "выборы", "правительств", "министр", "президент", "войн", "конфликт", "дипломат", "посол", "мид"],
        "business": ["бирж", "банк", "акци", "рынок", "экономик", "финанс", "инвест", "компани", "корпорац", "бизнес", "торгов", "сделк"],
        "technology": ["технолог", "it", "ai", "искусственный интеллект", "кибер", "программ", "софт", "hardware", "чип", "полупроводник"],
        "crypto": ["биткоин", "крипт", "блокчейн", "ethereum", "defi", "nft", "altcoin", "mining"],
        "science": ["научн", "исследован", "открыти", "теория", "квант", "био", "медицин", "ген", "космос", "марс"],
    }
    scores = {topic: sum(1 for word in words if word in text) for topic, words in contexts.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def _is_url_relevant_to_title(url: str, title: str) -> bool:
    """Проверяет, что URL изображения содержит ключевые слова из заголовка."""
    url_lower = url.lower()
    keywords = re.findall(r"\b[а-яёa-z]{4,}\b", title.lower())
    stop = {"бирж", "рынок", "новост", "новости", "стать", "публикац", "image", "photo", "picture", "stock", "getty", "shutter"}
    keywords = [k for k in keywords if k not in stop and len(k) >= 4]
    if not keywords:
        return True
    matches = sum(1 for kw in keywords if kw in url_lower)
    return matches >= 1 or matches >= max(1, len(keywords) // 5)


async def find_best_stock_image(title: str, summary: str = "") -> Optional[str]:
    """
    Ищет лучшее изображение через стоки.
    Улучшенная версия: строгая проверка релевантности по URL + ключевым словам.
    """
    from utils.text_utils import extract_top_keywords

    clean_title = _clean_title_for_search(title)
    queries = []
    keywords = extract_top_keywords(clean_title, summary, max_words=5)
    if keywords:
        context = _detect_topic_context(clean_title, summary)
        if context:
            queries.append(f"{keywords} {context}")
        queries.append(keywords)
    if clean_title and len(clean_title) > 3:
        queries.append(clean_title)
    seen_queries = set()
    unique_queries = []
    for q in queries:
        q_lower = q.lower().strip()
        if q_lower and q_lower not in seen_queries and len(q) > 3:
            seen_queries.add(q_lower)
            unique_queries.append(q)
    for query in unique_queries[:3]:
        if not query or len(query) < 3:
            continue
        urls = await search_all_stocks(query, max_per_source=3)
        for url in urls[:6]:
            if not _is_url_relevant_to_title(url, clean_title):
                logger.debug(f"❌ URL не релевантен заголовку: {url[:60]}...")
                continue
            if await _check_image_valid(url):
                logger.info(f"✅ Valid stock image found: {url[:60]}...")
                return url
            else:
                logger.debug(f"❌ Invalid/broken image: {url[:60]}...")
    logger.info(f"🚫 No valid stock images found for: {title[:60]}...")
    return None
