"""
Модуль для поиска и скриншотов твитов в новостях.

Если новость упоминает твит (Truth Social, Twitter, X),
пытаемся найти оригинальный твит и сделать скриншот.
"""

import re
from typing import Optional

import httpx
from playwright.async_api import async_playwright

from utils.logger import logger

# Паттерны для поиска упоминаний твитов в тексте
_TWEET_PATTERNS = [
    r"Truth Social",
    r"твиттер",
    r"Twitter",
    r"X\.com",
    r"соцсети",
    r"написал в",
    r"пост в",
    r"опубликовал в",
    r"@realDonaldTrump",
    r"@elonmusk",
]

# URL шаблоны для поиска твитов
_TWEET_URL_PATTERNS = [
    r"https?://(?:twitter\.com|x\.com)/\w+/status/\d+",
    r"https?://truthsocial\.com/[@\w]+/posts/\d+",
]


def contains_tweet_reference(text: str) -> bool:
    """Проверяет, упоминает ли текст твит или соцсеть."""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in _TWEET_PATTERNS:
        if pattern.lower() in text_lower:
            return True
    return False


def extract_tweet_url(text: str) -> Optional[str]:
    """Извлекает URL твита из текста, если есть."""
    for pattern in _TWEET_URL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


async def screenshot_tweet(
    url: str, output_path: str = "/tmp/tweet_screenshot.png"
) -> Optional[str]:
    """
    Делает скриншот твита через Playwright.

    Args:
        url: URL твита (twitter.com или truthsocial.com)
        output_path: Куда сохранить скриншот

    Returns:
        Путь к скриншоту или None если не удалось
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 800, "height": 1200})

            # Настройка для обхода блокировок
            await page.set_extra_http_headers(
                {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )

            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Ждем загрузки твита
            if "twitter.com" in url or "x.com" in url:
                await page.wait_for_selector("article[data-testid='tweet']", timeout=10000)
                # Делаем скриншот только твита
                tweet = await page.query_selector("article[data-testid='tweet']")
                if tweet:
                    await tweet.screenshot(path=output_path)
                else:
                    await page.screenshot(path=output_path, full_page=False)
            elif "truthsocial.com" in url:
                await page.wait_for_selector(".post-card", timeout=10000)
                post = await page.query_selector(".post-card")
                if post:
                    await post.screenshot(path=output_path)
                else:
                    await page.screenshot(path=output_path, full_page=False)
            else:
                await page.screenshot(path=output_path, full_page=False)

            await browser.close()
            logger.info(f"📸 Скриншот твита сохранен: {output_path}")
            return output_path

    except Exception as e:
        logger.warning(f"❌ Ошибка скриншота твита {url}: {e}")
        return None


async def find_tweet_screenshot(article: dict) -> Optional[str]:
    """
    Ищет твит в новости и делает скриншот.

    Args:
        article: Словарь с title, summary, link

    Returns:
        Путь к скриншоту или None
    """
    combined_text = f"{article.get('title', '')} {article.get('summary', '')}"

    # Проверяем, есть ли упоминание твита
    if not contains_tweet_reference(combined_text):
        return None

    # Пытаемся найти URL твита в тексте
    tweet_url = extract_tweet_url(combined_text)
    if tweet_url:
        return await screenshot_tweet(tweet_url)

    # Если URL нет в тексте, но есть упоминание Truth Social / Трампа,
    # можно попробовать найти через поиск (сложнее, требует API)

    return None
