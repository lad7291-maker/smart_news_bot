"""
Модуль генерации скриншотов веб-страниц через Playwright.

Используется для создания скриншотов источников новостей (как у Топор Live).
Скриншоты добавляются в pipeline изображений как уровень 5 — после Stock API,
перед SearXNG и fallback.

Требования: playwright (pip install playwright && playwright install chromium)
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

from utils.logger import logger

logger = logging.getLogger(__name__)

# Кэш скриншотов
SCREENSHOT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "image_cache", "screenshots"
)
os.makedirs(SCREENSHOT_CACHE_DIR, exist_ok=True)
SCREENSHOT_CACHE_MAX_AGE_HOURS = 24

# Размеры скриншота (Tele-friendly)
SCREENSHOT_WIDTH = 1200
SCREENSHOT_HEIGHT = 800
SCREENSHOT_FULL_PAGE = False  # Только viewport

# Домены, для которых скриншоты особенно полезны (новостные сайты с хорошим UI)
SCREENSHOT_FRIENDLY_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "cnn.com",
    "bloomberg.com",
    "nytimes.com",
    "wsj.com",
    "ft.com",
    "theguardian.com",
    "aljazeera.com",
    "france24.com",
    "dw.com",
    "euronews.com",
    "ria.ru",
    "tass.ru",
    "rbc.ru",
    "kommersant.ru",
    "interfax.ru",
    "rt.com",
    "lenta.ru",
    "meduza.io",
    "novayagazeta.eu",
    "politico.com",
    "axios.com",
    "thehill.com",
    "nbcnews.com",
    "cbsnews.com",
    "abcnews.go.com",
    "foxnews.com",
    "usatoday.com",
    "coindesk.com",
    "cointelegraph.com",
    "investing.com",
}

# Домены, где скриншоты бесполезны (paywall, anti-bot, плохой UI)
SCREENSHOT_UNFRIENDLY_DOMAINS = {
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "reddit.com",
}


def _get_cache_path(url: str) -> str:
    """Возвращает путь к кэшированному скриншоту."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(SCREENSHOT_CACHE_DIR, f"{url_hash}.png")


def _is_cache_valid(cache_path: str) -> bool:
    """Проверяет, валиден ли кэш."""
    if not os.path.exists(cache_path):
        return False
    age = os.path.getmtime(cache_path)
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc).timestamp() - age < SCREENSHOT_CACHE_MAX_AGE_HOURS * 3600


def _is_screenshot_friendly(url: str) -> bool:
    """Проверяет, подходит ли URL для скриншота."""
    from urllib.parse import urlparse

    domain = urlparse(url).netloc.lower()

    # Убираем www.
    if domain.startswith("www."):
        domain = domain[4:]

    # Чёрный список
    for bad in SCREENSHOT_UNFRIENDLY_DOMAINS:
        if bad in domain:
            return False

    # Белый список — только эти делаем скриншоты
    for good in SCREENSHOT_FRIENDLY_DOMAINS:
        if good in domain:
            return True

    # По умолчанию — не делаем скриншоты неизвестных доменов
    return False


async def take_screenshot(url: str, timeout: float = 30.0) -> Optional[bytes]:
    """
    Делает скриншот страницы через Playwright.

    Args:
        url: URL страницы
        timeout: Таймаут в секундах

    Returns:
        PNG bytes или None если не удалось
    """
    # Проверяем кэш
    cache_path = _get_cache_path(url)
    if _is_cache_valid(cache_path):
        logger.debug(f"💾 Скриншот из кэша: {url[:60]}...")
        with open(cache_path, "rb") as f:
            return f.read()

    # Проверяем, подходит ли домен
    if not _is_screenshot_friendly(url):
        logger.debug(f"🚫 Скриншот не подходит для домена: {url[:60]}...")
        return None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(
            "Playwright не установлен. Установите: pip install playwright && playwright install chromium"
        )
        return None

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": SCREENSHOT_WIDTH, "height": SCREENSHOT_HEIGHT},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            # Переходим на страницу
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

            # Ждём загрузки основного контента
            await page.wait_for_timeout(2000)

            # Скрываем cookie-баннеры, popups, рекламу
            await _hide_clutter(page)

            # Специальная обработка для BBC
            await _accept_cookies_bbc(page)

            # Пробуем сделать скриншот только статьи (без шапки, меню, баннеров)
            article_screenshot = await _screenshot_article_element(page)
            if article_screenshot:
                screenshot_bytes = article_screenshot
            else:
                # Fallback: скриншот viewport как раньше
                screenshot_bytes = await page.screenshot(
                    type="png",
                    full_page=SCREENSHOT_FULL_PAGE,
                )

            # MEM-FIX: browser закрывается в finally
            await browser.close()
            browser = None

            # Сохраняем в кэш
            with open(cache_path, "wb") as f:
                f.write(screenshot_bytes)

            logger.info(f"📸 Скриншот сделан: {url[:60]}... ({len(screenshot_bytes)} bytes)")
            return screenshot_bytes

    except Exception as e:
        logger.warning(f"❌ Ошибка скриншота {url[:60]}: {e}")
        return None
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass


async def _hide_clutter(page):
    """Скрывает cookie-баннеры, popups, рекламу на странице."""
    # Более агрессивное скрытие — по атрибутам aria-label, role, data-*
    hide_scripts = [
        # Cookie баннеры (по классам, id, aria)
        "document.querySelectorAll('[class*=cookie], [class*=Cookie], [id*=cookie], [id*=Cookie], [class*=consent], [class*=Consent], [class*=gdpr], [class*=GDPR], [class*=privacy], [class*=banner]').forEach(el => { el.style.display = 'none'; el.style.visibility = 'hidden'; });",
        # Popups, модальные окна, оверлеи
        "document.querySelectorAll('[class*=popup], [class*=modal], [class*=overlay], [class*=dialog], [role=dialog], [aria-modal=true], [class*=backdrop], [class*=mask]').forEach(el => { el.style.display = 'none'; el.style.visibility = 'hidden'; });",
        # Реклама
        "document.querySelectorAll('[class*=ad], [class*=Ad], [id*=ad], [id*=Ad], [class*=advert], [class*=sponsor], [data-ad]').forEach(el => { el.style.display = 'none'; el.style.visibility = 'hidden'; });",
        # Newsletter подписки
        "document.querySelectorAll('[class*=newsletter], [class*=subscribe], [class*=signup], [class*=follow]').forEach(el => { el.style.display = 'none'; el.style.visibility = 'hidden'; });",
        # Фиксированные header/footer (делаем static вместо fixed)
        "document.querySelectorAll('header, footer, [class*=sticky], [class*=fixed]').forEach(el => { if (getComputedStyle(el).position === 'fixed' || getComputedStyle(el).position === 'sticky') { el.style.position = 'static'; } });",
        # Убираем blur/opacity на body (некоторые сайты размывают фон при модалке)
        "document.body.style.overflow = 'auto'; document.body.style.filter = 'none'; document.documentElement.style.overflow = 'auto';",
        # Скрываем iframes, которые могут быть cookie-баннерами
        "document.querySelectorAll('iframe').forEach(iframe => { if (iframe.src && (iframe.src.includes('privacy') || iframe.src.includes('cookie') || iframe.src.includes('consent') || iframe.src.includes('cmp') || iframe.src.includes('gdpr'))) { iframe.style.display = 'none'; iframe.style.visibility = 'hidden'; } });",
        # Скрываем нижние баннеры (fixed bottom)
        "document.querySelectorAll('[class*=bottom], [class*=footer], [id*=bottom]').forEach(el => { if (getComputedStyle(el).position === 'fixed' && getComputedStyle(el).bottom === '0px') { el.style.display = 'none'; } });",
    ]

    for script in hide_scripts:
        try:
            await page.evaluate(script)
        except Exception:
            pass

    # Кликаем "I agree" / "Accept" / "Do not agree" на cookie-баннерах если есть
    accept_buttons = [
        'button:has-text("I agree")',
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        'button:has-text("Agree")',
        'button:has-text("OK")',
        'button:has-text("Do not agree")',
        'button:has-text("No thanks")',
        'button:has-text("Reject")',
        'button:has-text("Decline")',
        '[aria-label*="Accept"]',
        '[aria-label*="agree"]',
    ]

    for selector in accept_buttons:
        try:
            button = await page.query_selector(selector)
            if button:
                await button.click()
                await page.wait_for_timeout(500)
                break
        except Exception:
            pass

    # Дополнительная задержка после скрытия
    await page.wait_for_timeout(1000)


async def _accept_cookies_bbc(page):
    """Специальная обработка для BBC cookie banner (iframe-based)."""
    try:
        # BBC cookie banner может быть в iframe (cdn.privacy-mgmt.com)
        # Ищем кнопку во всех фреймах
        for frame in page.frames:
            try:
                # Пробуем найти кнопку "I do not agree" (отклонить cookies)
                btn = await frame.query_selector('button:has-text("I do not agree")')
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    return True

                # Или "Yes, I agree" (главный фрейм BBC)
                btn2 = await frame.query_selector('button:has-text("Yes, I agree")')
                if btn2:
                    await btn2.click()
                    await page.wait_for_timeout(1500)
                    return True

                # Или просто "I agree"
                btn3 = await frame.query_selector('button:has-text("I agree")')
                if btn3:
                    await btn3.click()
                    await page.wait_for_timeout(1500)
                    return True

            except Exception:
                pass
    except Exception:
        pass
    return False


async def _screenshot_article_element(page) -> Optional[bytes]:
    """
    Пытается сделать скриншот только элемента со статьёй (не всей страницы).
    Возвращает PNG bytes или None если не удалось найти элемент.
    """
    # CSS-селекторы для основного контента статьи на разных сайтах
    article_selectors = [
        # Общие
        "article",
        "main",
        "[role='main']",
        ".article-content",
        ".post-content",
        ".entry-content",
        ".story-body",
        ".news-text",
        "[itemprop='articleBody']",
        ".content",
        # Интерфакс
        ".article",
        ".article__text",
        ".article__content",
        # РИА
        ".article__block",
        ".article__article-image",
        # RT
        ".article__text",
        ".article__summary",
        # ТАСС
        ".news-content",
        ".text-content",
        # Лента
        ".b-topic__content",
        ".topic-content",
        # РБК
        ".article__content",
        ".article__text",
        # Коммерсант
        ".article_text",
        ".doc__text",
        # Медуза
        ".GeneralMaterial-module__content",
        ".MaterialContent",
        # BBC
        "[data-component='text-block']",
        ".ssrcss-7uxr49-RichTextContainer",
        # Reuters
        ".article-body__content__17Yit",
        ".ArticleBodyWrapper",
        # NYT
        ".articleBody",
        "section[name='articleBody']",
        # Guardian
        ".article-body-commercial-selector",
        # Bloomberg
        ".body-content",
        # CNN
        ".article__content",
        ".zn-body__paragraph",
        # Al Jazeera
        ".article-content",
        # Politico
        ".story-text",
        # Axios
        ".article-body",
    ]

    for selector in article_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Проверяем, что элемент видимый и имеет размер
                box = await element.bounding_box()
                if box and box["width"] > 200 and box["height"] > 200:
                    screenshot = await element.screenshot(type="png")
                    logger.info(f"📸 Скриншот элемента {selector}: {len(screenshot)} bytes")
                    return screenshot
        except Exception:
            continue
    return None


def _is_valid_screenshot(img: Image.Image) -> bool:
    """
    Проверяет, что скриншот не является битым/блокировочным/пустым.

    Проверки:
    1. Не слишком маленький (менее 10KB обычно — блокировочная страница)
    2. Не однотонный/белый (пустой скриншот)
    3. Не серый экран ошибки
    """
    try:
        # Проверяем размер
        width, height = img.size
        if width < 100 or height < 100:
            logger.info(f"🚫 Скриншот слишком маленький ({width}x{height}), отклоняем")
            return False

        # Проверяем на однотонность/пустоту
        # Конвертируем в RGB и берём миниатюру для анализа
        img_rgb = img.convert("RGB") if img.mode != "RGB" else img

        # Уменьшаем для быстрого анализа (но не слишком сильно чтобы сохранить детали)
        small = img_rgb.resize((100, 100))
        pixels = list(small.get_flattened_data())

        # Считаем средний цвет и стандартное отклонение
        r_vals = [p[0] for p in pixels]
        g_vals = [p[1] for p in pixels]
        b_vals = [p[2] for p in pixels]

        avg_r = sum(r_vals) / len(r_vals)
        avg_g = sum(g_vals) / len(g_vals)
        avg_b = sum(b_vals) / len(b_vals)

        # Стандартное отклонение
        def stddev(vals, avg):
            return (sum((x - avg) ** 2 for x in vals) / len(vals)) ** 0.5

        std_r = stddev(r_vals, avg_r)
        std_g = stddev(g_vals, avg_g)
        std_b = stddev(b_vals, avg_b)
        avg_std = (std_r + std_g + std_b) / 3

        # Если изображение почти однотонное (std < 3) — скорее всего пустое/белое
        if avg_std < 3:
            logger.info(f"🚫 Скриншот однотонный (std={avg_std:.1f}), отклоняем")
            return False

        # Если изображение очень светлое (белый фон) и мало деталей
        avg_brightness = (avg_r + avg_g + avg_b) / 3
        if avg_brightness > 250 and avg_std < 10:
            logger.info(
                f"🚫 Скриншот почти белый (brightness={avg_brightness:.1f}, std={avg_std:.1f}), отклоняем"
            )
            return False

        # Дополнительная проверка: количество уникальных цветов
        unique_colors = len(set(pixels))
        if unique_colors < 50:
            logger.info(f"🚫 Скриншот слишком мало цветов ({unique_colors}), отклоняем")
            return False

        return True
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки скриншота: {e}")
        return True  # В случае ошибки — пропускаем


async def process_screenshot_for_telegram(
    url: str,
    article_title: str = "",
    timeout: float = 30.0,
) -> Optional[bytes]:
    """
    Полный pipeline: скриншот → обрезка → JPEG → bytes.

    Args:
        url: URL страницы
        article_title: Заголовок (для логов)
        timeout: Таймаут

    Returns:
        JPEG bytes или None
    """
    png_bytes = await take_screenshot(url, timeout)
    if not png_bytes:
        return None

    try:
        from utils.image_processor import crop_to_aspect, image_to_bytes, resize_if_needed

        # Конвертируем PNG в PIL Image
        img = Image.open(__import__("io").BytesIO(png_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Проверяем, что скриншот не битый (не блокировочная страница, не пустой)
        if not _is_valid_screenshot(img):
            logger.warning(f"🚫 Скриншот отклонён (битый/блокировочный): {url[:60]}...")
            return None

        # Обрезаем под 16:9 для Telegram
        img = crop_to_aspect(img, 16 / 9)

        # Уменьшаем если слишком большое
        img = resize_if_needed(img)

        # Конвертируем в JPEG
        return image_to_bytes(img, format="JPEG", quality=85)

    except Exception as e:
        logger.warning(f"❌ Ошибка обработки скриншота: {e}")
        return None


async def find_screenshot_image(article: Dict[str, Any]) -> Optional[str]:
    """
    Проверяет, можно ли сделать скриншот для статьи.
    Возвращает URL (для совместимости с pipeline) или None.

    Args:
        article: Словарь с article (должен содержать 'link')

    Returns:
        URL статьи (если скриншот возможен) или None
    """
    link = article.get("link", "")
    if not link or not link.startswith(("http://", "https://")):
        return None

    if not _is_screenshot_friendly(link):
        return None

    # Проверяем, есть ли уже кэш
    cache_path = _get_cache_path(link)
    if _is_cache_valid(cache_path):
        return link  # Вернём URL — process_image_for_telegram обработает через кэш

    # Проверяем доступность страницы (GET вместо HEAD для надёжных доменов)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Для надёжных новостных доменов делаем GET (HEAD может быть заблокирован)
            from urllib.parse import urlparse

            domain = urlparse(link).netloc.lower().replace("www.", "")
            is_reliable = domain in SCREENSHOT_FRIENDLY_DOMAINS

            if is_reliable:
                # Для надёжных доменов — сразу разрешаем скриншот без проверки
                return link

            resp = await client.head(link)
            if resp.status_code >= 400:
                return None
    except Exception:
        # Если HEAD не сработал — для надёжных доменов всё равно разрешаем
        from urllib.parse import urlparse

        domain = urlparse(link).netloc.lower().replace("www.", "")
        if domain in SCREENSHOT_FRIENDLY_DOMAINS:
            return link
        return None

    return link


if __name__ == "__main__":
    # Тест
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))

    async def test():
        # Тест 1: Reuters
        url1 = "https://www.reuters.com/world/"
        result1 = await take_screenshot(url1)
        print(f"Reuters screenshot: {len(result1) if result1 else 'None'} bytes")

        # Тест 2: Неподходящий домен
        url2 = "https://twitter.com/elonmusk"
        result2 = await find_screenshot_image({"link": url2})
        print(f"Twitter screenshot allowed: {result2 is not None}")

        # Тест 3: Кэш
        if result1:
            cached = await take_screenshot(url1)
            print(f"Cached screenshot: {len(cached) if cached else 'None'} bytes")

    asyncio.run(test())
