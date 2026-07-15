"""
Модуль извлечения изображений из RSS-записей и HTML-страниц.

Источники (по приоритету):
1. RSS-нативные: <enclosure>, <media:content>, <media:thumbnail>
   — оригинальное фото без текста, лучший источник
2. Первое фото из HTML статьи (article/main img)
   — оригинальное фото из текста статьи
3. Open Graph: <meta property="og:image">
   — фильтруем "социальные карточки" с наложенным текстом

P1-002: extract_image_from_html переписан на httpx.AsyncClient.
"""

import logging
from typing import Any, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from config import config

logger = logging.getLogger(__name__)

_SOURCE_PENALTIES = {
    "interfax.ru/ftproot/textphotos/": -30,
    "interfax.ru/ftproot/photos/": -20,
}

# Минимальные размеры контентного изображения (px).
# Меньше — считаем иконкой/трекером, а не фото статьи.
_MIN_IMAGE_WIDTH = 200
_MIN_IMAGE_HEIGHT = 150


def _apply_source_penalty(url, score):
    if not url:
        return score
    lower = url.lower()
    for pattern, penalty in _SOURCE_PENALTIES.items():
        if pattern in lower:
            new_score = max(0, score + penalty)
            logger.debug(f"Source penalty {pattern}: {score} -> {new_score}")
            return new_score
    return score


# Штрафы за известные generic-источники (мусорные изображения)


def _check_image_size(soup: BeautifulSoup, img_src: str) -> Tuple[bool, int, int]:
    """
    Проверяет размер изображения по атрибутам width/height в HTML.

    Returns:
        (is_valid, width, height)
    """
    # Ищем img тег с этим src
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src == img_src or img_src.endswith(src) or src.endswith(img_src.split("/")[-1]):
            width = img.get("width", "")
            height = img.get("height", "")

            # Парсим размеры
            try:
                w = int(width) if width and str(width).isdigit() else 0
                h = int(height) if height and str(height).isdigit() else 0

                if w > 0 and h > 0:
                    is_valid = w >= _MIN_IMAGE_WIDTH and h >= _MIN_IMAGE_HEIGHT
                    return is_valid, w, h
            except (ValueError, TypeError):
                pass

    # Если размеры не найдены — считаем валидным (проверим позже)
    return True, 0, 0


# OG-изображения, которые на самом деле "социальные карточки"
_OG_BAD_PATTERNS = {
    "/sharing/",
    "/social/",
    "/og-image",
    "/og_image",
    "/card",
    "/preview",
    "/thumb_large",
    # "/article_main",  # может быть реальное фото статьи
    "cdnn21.img.ria.ru/images/sharing/",  # RIA sharing — соц-карточки
    "russian.rt.com/static/blocks/og-img/",  # RT OG — соц-карточка с текстом
    "rt.com/static/blocks/og-img/",
    "interfax.ru/aspimg/",  # Interfax OG — соц-карточка с логотипом и заголовком
    "interfax.com/aspimg/",
    "flagcdn.com",  # Флаги стран — не релевантные фото
    "cryptologos.cc",  # Логотипы крипто — не релевантные фото
}

# Домены с хорошими OG
_OG_GOOD_DOMAINS = {
    "nytimes.com",
    "static01.nyt.com",
    "bbc.com",
    "bbc.co.uk",
    "ichef.bbci.co.uk",
    "reuters.com",
    "reutersmedia.net",
    "apnews.com",
    "bloomberg.com",
    "cnn.com",
    "cdn.cnn.com",
    "theguardian.com",
    "aljazeera.com",
    "france24.com",
    "dw.com",
    "euronews.com",
    "ft.com",
    "wsj.com",
    "nbcnews.com",
    "cbsnews.com",
    # Russian news agencies — their photos are relevant by default
    "interfax.ru",
    "interfax.com",
    "tass.ru",
    "tass.com",
    "ria.ru",
    "rian.ru",
    "rbc.ru",
    "rbk.ru",
    "lenta.ru",
    "russian.rt.com",
    "rt.com",
    "mf.b37mrtl.ru",  # RT CDN — реальные фото статей
    "vz.ru",
    "vedomosti.ru",
    "kommersant.ru",
    "gazeta.ru",
    "newsru.com",
    "abcnews.go.com",
    "foxnews.com",
    "a57.foxnews.com",
    "static.foxnews.com",
    "usatoday.com",
    "latimes.com",
    "chicagotribune.com",
    "cnbc.com",
    "image.cnbcfm.com",
    "marketwatch.com",
    "investing.com",
    "seekingalpha.com",
    "businessinsider.com",
    "forbes.com",
    "fortune.com",
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "arstechnica.com",
    "engadget.com",
    "cnet.com",
    "zdnet.com",
    "coindesk.com",
    "cointelegraph.com",
}


def _is_og_social_card(img_url: str) -> bool:
    """Проверяет, является ли OG-изображение социальной карточкой."""
    if not img_url:
        return True
    url_lower = img_url.lower()
    for bad in _OG_BAD_PATTERNS:
        if bad in url_lower:
            return True
    return False


def _is_news_domain(img_url: str) -> bool:
    """Проверяет, принадлежит ли URL известному новостному домену."""
    if not img_url:
        return False
    url_lower = img_url.lower()
    _NEWS_DOMAINS = {
        "interfax.ru",
        "interfax.com",
        "tass.ru",
        "tass.com",
        "ria.ru",
        "rian.ru",
        "rbc.ru",
        "rbk.ru",
        "lenta.ru",
        "russian.rt.com",
        "rt.com",
        "vz.ru",
        "vedomosti.ru",
        "kommersant.ru",
        "gazeta.ru",
        "newsru.com",
        "nytimes.com",
        "bbc.com",
        "bbc.co.uk",
        "reuters.com",
        "apnews.com",
        "bloomberg.com",
        "cnn.com",
        "theguardian.com",
        "france24.com",
        "dw.com",
        "euronews.com",
    }
    return any(domain in url_lower for domain in _NEWS_DOMAINS)


def _is_og_reliable_domain(img_url: str) -> bool:
    """Проверяет, принадлежит ли URL домену с хорошими OG."""
    if not img_url:
        return False
    url_lower = img_url.lower()
    return any(domain in url_lower for domain in _OG_GOOD_DOMAINS)


def _is_rss_social_card(img_url: str) -> bool:
    """Проверяет, является ли RSS-изображением социальной карточкой."""
    if not img_url:
        return True
    url_lower = img_url.lower()
    # Только явно рекламные/шеринговые баннеры — остальное пропускаем
    # Примечание: mf.b37mrtl.ru — это CDN RT с реальными фото, не соц-карточки
    if "cdnn21.img.ria.ru/images/sharing/" in url_lower:
        return True
    # RT OG — это соц-карточка с наложенным текстом, не фото
    if "russian.rt.com/static/blocks/og-img/" in url_lower:
        return True
    if "rt.com/static/blocks/og-img/" in url_lower:
        return True
    return False


def extract_image_from_rss_entry(entry: Any) -> Optional[str]:
    """Извлекает URL изображения из записи feedparser."""
    enclosures = getattr(entry, "enclosures", None)
    if enclosures:
        for enc in enclosures:
            if isinstance(enc, dict):
                enc_type = enc.get("type", "")
                href = enc.get("href", "")
                if enc_type.startswith("image/") and href:
                    if not _is_rss_social_card(href):
                        return href
                if href and any(
                    href.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")
                ):
                    if not _is_rss_social_card(href):
                        return href

    media_content = getattr(entry, "media_content", None)
    if media_content:
        for mc in media_content:
            if isinstance(mc, dict):
                medium = mc.get("medium", "")
                url = mc.get("url", "")
                if medium == "image" and url:
                    if not _is_rss_social_card(url):
                        return url
                if url and any(
                    url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")
                ):
                    if not _is_rss_social_card(url):
                        return url

    media_thumbnail = getattr(entry, "media_thumbnail", None)
    if media_thumbnail:
        for mt in media_thumbnail:
            if isinstance(mt, dict):
                url = mt.get("url", "")
                if url and not _is_rss_social_card(url):
                    return url

    return None


def _extract_first_article_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Извлекает первое фото из тела статьи (article/main/etc)."""
    for selector in (
        "article img",
        "main img",
        ".article-content img",
        ".post-content img",
        ".entry-content img",
        # RIA Novosti
        ".article__block img",
        ".article__article-image img",
        ".media img",
        # RT
        ".article__text img",
        ".article__summary img",
        # TASS
        ".news-content img",
        ".text-content img",
        # Lenta
        ".b-topic__content img",
        ".topic-content img",
        # General
        "[itemprop='articleBody'] img",
        ".content img",
        ".story-body img",
        ".news-text img",
    ):
        img = soup.select_one(selector)
        if img and img.get("src"):
            src = img["src"].strip()
            if src.startswith(("http://", "https://")):
                return src
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                from urllib.parse import urljoin

                return urljoin(base_url, src)
    return None


async def extract_image_from_html(
    url: str, timeout: int = 8
) -> tuple[Optional[str], Optional[str]]:
    """
    Парсит HTML-страницу и извлекает изображение (async).

    Returns:
        (og_image, article_image) — оба могут быть None
    """
    try:
        headers = {"User-Agent": config.USER_AGENT}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            text = resp.text

        soup = BeautifulSoup(text, "html.parser")

        # 1. Open Graph
        og_image = None
        for prop in ("og:image", "og:image:url"):
            tag = soup.find("meta", property=prop)
            if tag and tag.get("content"):
                img_url = tag["content"].strip()
                if img_url.startswith(("http://", "https://")):
                    og_image = img_url
                    break

        if not og_image:
            tag = soup.find("meta", attrs={"name": "twitter:image"})
            if tag and tag.get("content"):
                img_url = tag["content"].strip()
                if img_url.startswith(("http://", "https://")):
                    og_image = img_url

        # 2. Первое фото из статьи
        article_image = _extract_first_article_image(soup, url)

        return og_image, article_image

    except Exception as e:
        logger.debug(f"HTML parse failed for {url[:60]}: {e}")

    return None, None


def _is_image_relevant_to_title(img_url: str, title: str) -> bool:
    """Проверяет, содержит ли URL изображения ключевые слова из заголовка."""
    if not img_url or not title:
        return True  # Если нечего проверять — пропускаем

    from utils.searxng_client import _TRANSLIT_MAP, _normalize_word
    from utils.text_utils import extract_keywords

    title_keywords = extract_keywords(title, min_length=4)
    img_lower = img_url.lower()

    # Проверяем, есть ли хотя бы одно ключевое слово в URL изображения
    matches = 0
    for kw in title_keywords:
        kw_lower = kw.lower()
        if kw_lower in img_lower:
            matches += 1
            continue
        # Проверяем нормализованную форму
        kw_norm = _normalize_word(kw)
        if kw_norm in img_lower:
            matches += 1
            continue
        # Проверяем транслитерацию
        if kw_norm in _TRANSLIT_MAP:
            eng_variant = _TRANSLIT_MAP[kw_norm]
            if eng_variant in img_lower:
                matches += 1
                continue

    # Если есть хотя бы 1 совпадение — считаем релевантным
    return matches >= 1


async def extract_image_for_article(
    entry: Any, article_link: str, title: str = ""
) -> Optional[str]:
    """
    Полный pipeline извлечения изображения для статьи (async).

    Приоритет:
    1. RSS-нативные — оригинальное фото (с проверкой релевантности)
    2. Первое фото из HTML статьи — оригинал из текста
    3. OG от надёжных доменов
    4. OG от остальных — фильтруем соц-карточки
    """
    result = await extract_image_with_score(entry, article_link, title)
    return result[0] if result else None


async def extract_image_with_score(
    entry: Any, article_link: str, title: str = ""
) -> Optional[tuple[str, int, str]]:
    """
    Полный pipeline извлечения изображения с оценкой релевантности.

    Returns:
        (url, score, source) или None
        score: 0-100, где:
            70-100 = высокая уверенность (RSS/OG от надёжных доменов)
            50-69  = средняя уверенность (article img, OG обычные)
            30-49  = сомнительная (нужен LLM judge)
            <30    = нерелевантное (отбросить)
    """
    # Шаг 1: RSS (без проверки keywords — enclosure это оригинальное фото)
    rss_image = extract_image_from_rss_entry(entry)
    if rss_image:
        # RSS enclosure — оригинальное фото, всегда релевантно
        return (rss_image, _apply_source_penalty(rss_image, 75), "rss")

    if not article_link or not article_link.startswith(("http://", "https://")):
        return None

    # Шаг 2: Парсим HTML
    og_image, article_image = await extract_image_from_html(article_link)

    # Шаг 2a: OG от надёжных доменов — лучший источник, проверяем ПЕРВЫМ
    # Но фильтруем соц-карточки
    if og_image and _is_og_reliable_domain(og_image):
        if not _is_og_social_card(og_image):
            return (og_image, _apply_source_penalty(og_image, 80), "og")
        logger.debug(f"🚫 OG соц-карточка от доверенного домена отклонена: {og_image[:60]}...")

    # Шаг 2b: Первое фото из статьи
    if article_image:
        if not _is_og_social_card(article_image):
            # Для надёжных новостных доменов — считаем релевантным по умолчанию
            if _is_news_domain(article_image) or _is_image_relevant_to_title(article_image, title):
                logger.debug(f"🖼 Article image: {article_image[:80]}...")
                return (article_image, _apply_source_penalty(article_image, 60), "article")
            else:
                # Нерелевантное фото из статьи — сомнительный score
                logger.debug(f"⚠️ Article image сомнительно: {article_image[:80]}...")
                return (article_image, _apply_source_penalty(article_image, 40), "article")

    # Шаг 3: OG от остальных доменов
    if og_image:
        if not _is_og_social_card(og_image):
            # Проверяем релевантность
            if _is_image_relevant_to_title(og_image, title):
                return (og_image, _apply_source_penalty(og_image, 55), "og")
            else:
                return (og_image, _apply_source_penalty(og_image, 35), "og")
        logger.debug(f"🚫 OG соц-карточка отклонена: {og_image[:60]}...")

    return None
