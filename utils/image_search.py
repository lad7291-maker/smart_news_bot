"""
Модуль поиска изображений к новостям через DuckDuckGo (ddgs).

Улучшенная версия:
1. AI-экстрактор ключевых сущностей из заголовка + summary
2. Множественный поиск (до 10 картинок)
3. Фильтрация по качеству (размер, формат, источник)
4. Ранжирование по релевантности запросу
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ddgs import DDGS

from ai_core.routerai_provider import routerai_provider
from translator import translate_to_english
from utils.logger import logger

# Источники, которые точно на русском языке
_RUSSIAN_SOURCES = {
    "Habr",
    "VC",
    "Science",
    "Security",
    "Interfax",
    "RT",
    "RIA",
}

# Нежелательные домены / паттерны в URL
_BAD_DOMAINS = {
    "icon",
    "favicon",
    "logo",
    "avatar",
    "profile",
    "button",
    "badge",
    "banner",
    "sprite",
    "ui-",
    "widget",
    "emoji",
    "smiley",
    "sticker",
}

# Разрешённые новостные домены (whitelist)
# Если не пустой — принимаем ТОЛЬКО изображения с этих доменов
_NEWS_DOMAINS = {
    # Международные агентства
    "reuters.com",
    "apnews.com",
    "ap.org",
    "afp.com",
    "gettyimages.com",
    "gettyimages.",
    "shutterstock.com",
    # Крупные СМИ
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
    "nbcnews.com",
    "cbsnews.com",
    "abcnews.go.com",
    "foxnews.com",
    "usatoday.com",
    "latimes.com",
    "chicagotribune.com",
    # Бизнес/финансы
    "cnbc.com",
    "marketwatch.com",
    "investing.com",
    "seekingalpha.com",
    "businessinsider.com",
    "forbes.com",
    "fortune.com",
    # Технологии
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "arstechnica.com",
    "engadget.com",
    "cnet.com",
    "zdnet.com",
    # Россия
    "ria.ru",
    "tass.ru",
    "rbc.ru",
    "kommersant.ru",
    "vedomosti.ru",
    "interfax.ru",
    "lenta.ru",
    "gazeta.ru",
    "mk.ru",
    "kp.ru",
    "rt.com",
    "sputniknews.com",
    "tsargrad.tv",
    # Другие регионы
    "xinhuanet.com",
    "scmp.com",
    "japantimes.co.jp",
    "straitstimes.com",
    "hindustantimes.com",
    "timesofindia.indiatimes.com",
    # Фото-агентства
    "alamy.com",
    "alamyimages.",
    "dpa.com",
    "epa.eu",
    # Популярные новостные платформы
    "substack.com",
    "medium.com",
    "hashnode.com",
    # Образовательные / аналитические
    "brookings.edu",
    "carnegieendowment.org",
    "cfr.org",
    "pewresearch.org",
    "statista.com",
    "ourworldindata.org",
    # Специализированные
    "spacenews.com",
    "defensenews.com",
    "navalnews.com",
    "aviationweek.com",
    "flightglobal.com",
    # Новостные CDN и хосты изображений (конкретные)
    "newsrally.com",
    "img.newsrally.com",
    "media.cnn.com",
    "cdn.cnn.com",
    "static.foxnews.com",
    "a57.foxnews.com",
    "ichef.bbci.co.uk",
    "c.files.bbci.co.uk",
    "cloudfront.net",
    "akamaized.net",
    "wp.com",
    "wordpress.com",
    "twimg.com",
    "twitter.com",
    "x.com",
    "fbcdn.net",
    "instagram.com",
    "ytimg.com",
    "youtube.com",
    "googleusercontent.com",
    "ggpht.com",
    "pinimg.com",
    "pinterest.com",
    "redditmedia.com",
    "redd.it",
    "imgur.com",
    "i.imgur.com",
    "wikimedia.org",
    "wikipedia.org",
    # Флаги стран и крипто-логотипы (fallback CDN — FEAT-009)
    "flagcdn.com",
    "cryptologos.cc",
}

# Предпочтительные форматы изображений (по убыванию приоритета)
_GOOD_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_BAD_EXTENSIONS = (".svg", ".gif", ".bmp", ".ico")


def _is_russian_source(source: str) -> bool:
    return source in _RUSSIAN_SOURCES


def _extract_keywords_heuristic(title: str, summary: str) -> str:
    """
    Эвристический экстрактор ключевых слов.
    Используется как fallback, если AI недоступен.
    """
    text = f"{title} {summary}".strip()
    # Убираем лишнее
    text = re.sub(r"[^\w\s\-]", " ", text)
    words = text.split()
    # Берём первые 10 значимых слов (исключаем короткие стоп-слова)
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "этот",
        "эта",
        "это",
        "как",
        "для",
        "что",
        "где",
        "когда",
        "кто",
        "из",
        "на",
        "в",
        "и",
        "или",
        "но",
        "за",
        "по",
        "от",
        "до",
        "со",
    }
    keywords = [w for w in words if len(w) > 2 and w.lower() not in stop_words][:12]
    return " ".join(keywords)


async def _extract_keywords_ai(title: str, summary: str) -> Optional[str]:
    """
    Использует AI для извлечения 3-5 ключевых сущностей из новости,
    которые лучше всего подходят для поиска изображения.

    Возвращает строку с ключевыми словами на английском,
    или None если AI недоступен / не сработал.
    """
    try:
        from ai_core.ai_provider import ai_provider

        prompt = f"""Ты — помощник по подбору изображений к новостям.

Задача: извлечь из новости 3-5 ключевых сущностей для поиска АКТУАЛЬНОГО фото.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Выбирай ТОЛЬКО главных действующих лиц и актуальные объекты этой конкретной новости
2. НЕ включай людей/объекты, которые упоминаются только в контексте "раньше", "прежде", "в прошлом"
3. НЕ включай упоминания о прошлых событиях или сравнениях с прошлым
4. Если новость про "X сделал Y, в отличие от Z" — включай только X и Y, НЕ Z
5. Если речь о текущих действиях администрации — укажи текущего лидера, НЕ предыдущего

Примеры:
- "Лавров сказал, что Трамп вводит санкции, в отличие от Байдена" → lavrov, trump, sanctions
- "Путин встретился с Си" → putin, xi
- "Bitcoin вырос после решения SEC" → bitcoin, sec

Ответь ТОЛЬКО ключевыми словами на английском языке через запятую, без пояснений.

Заголовок: {title}
Текст: {summary[:600] if summary else ""}

Ключевые слова:"""
        if routerai_provider.available:
            payload = {
                "model": routerai_provider.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты извлекаешь ключевые слова для поиска изображений. Отвечай только списком слов через запятую, без пояснений.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 60,
            }
            data = await routerai_provider._make_request(payload, timeout=20, retries=3)
            keywords = data["choices"][0]["message"]["content"].strip()
            # Очистка от markdown и лишнего
            keywords = re.sub(r"[\*\-\#\`\n\r]", "", keywords).strip()
            # Убираем "Keywords:" или "Ключевые слова:" если AI их добавил
            keywords = re.sub(
                r"^(keywords|ключевые слова|key words)[\s:]*", "", keywords, flags=re.IGNORECASE
            )
            if keywords and len(keywords) > 3:
                logger.info(f"🤖 AI keywords: {keywords[:100]}")
                return keywords
    except Exception as e:
        logger.debug(f"AI keyword extraction failed: {e}")
    return None


def _extract_top_keywords(title: str, summary: str, max_words: int = 5) -> str:
    """Извлекает топ-N ключевых слов из заголовка для поиска фото."""
    text = f"{title} {summary[:200]}".strip()
    # Убираем даты, дни недели, числа
    months = r"январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]"
    days = r"понедельник|вторник|сред[аы]|четверг|пятниц[аы]|суббот[аы]|воскресень[ея]"
    text = re.sub(r"\d{1,2}\s*" + months + r"", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"" + months + r"\s*\d{1,4}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"" + days + r"", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"20\d{2}", " ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()

    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "this",
        "that",
        "it",
        "its",
        "said",
        "says",
        "say",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "about",
        "into",
        "than",
        "only",
        "other",
        "some",
        "time",
        "year",
        "week",
        "day",
        "этот",
        "эта",
        "это",
        "как",
        "для",
        "что",
        "где",
        "когда",
        "кто",
        "из",
        "на",
        "в",
        "и",
        "или",
        "но",
        "за",
        "по",
        "от",
        "до",
        "со",
        "при",
        "об",
        "про",
        "под",
        "над",
        "перед",
        "после",
        "между",
        "через",
        "новый",
        "новое",
        "новая",
        "новые",
        "последний",
        "последнее",
        "последняя",
        "сегодня",
        "вчера",
        "сейчас",
        "только",
        "последние",
        "экстренно",
        "срочно",
    }

    keywords = []
    seen = set()

    # Сначала ищем имена собственные
    proper_names = re.findall(r"\b[А-ЯЁ][а-яё]+\b|\b[A-Z][a-z]+\b", title)
    for name in proper_names:
        n = name.lower()
        if n not in stop_words and len(n) > 2 and n not in seen:
            keywords.append(name)
            seen.add(n)
            if len(keywords) >= max_words:
                break

    for word in words:
        w = word.lower().strip()
        if w not in stop_words and len(w) > 3 and w not in seen:
            keywords.append(word)
            seen.add(w)
            if len(keywords) >= max_words:
                break

    return " ".join(keywords)


def _build_image_query(title: str, summary: str, source: str) -> str:
    """
    Формирует КОРОТКИЙ поисковый запрос для картинки (3-5 ключевых слов).
    Улучшенная версия: запрос до 80 символов, поисковики справляются лучше.
    """
    keywords = _extract_top_keywords(title, summary, max_words=5)

    if _is_russian_source(source):
        translated = translate_to_english(keywords)
        if translated and translated != keywords:
            keywords = translated

    query = f"{keywords} news"
    if len(query) > 100:
        query = query[:100].rsplit(" ", 1)[0] + " news"

    return query


def _score_image(url: str, title_keywords: set) -> int:
    """
    Оценивает качество изображения по URL.
    Возвращает score (чем больше, тем лучше).
    """
    import re

    score = 0
    lower = url.lower()

    # Штраф за плохие расширения
    if any(lower.endswith(ext) for ext in _BAD_EXTENSIONS):
        score -= 50

    # Бонус за хорошие расширения
    if any(lower.endswith(ext) for ext in _GOOD_EXTENSIONS):
        score += 10

    # Штраф за нежелательные домены/паттерны
    for bad in _BAD_DOMAINS:
        if bad in lower:
            score -= 30
            break

    # Бонус если URL содержит ключевые слова из заголовка
    for kw in title_keywords:
        if kw.lower() in lower:
            score += 15

    # --- ВРЕМЕННОЙ ФИЛЬТР: штраф за старые даты в URL, бонус за свежие ---
    year_match = re.search(r"/(20)(\d{2})/", lower)
    if year_match:
        year = int(year_match.group(1) + year_match.group(2))
        if year >= 2026:
            score += 15
        elif year == 2025:
            score += 10
        elif year == 2024:
            score += 0
        elif year <= 2023:
            score -= 20

    # --- ПРИОРИТЕТ НОВОСТНЫМ АГЕНТСТВАМ ---
    top_news_domains = {
        "reuters": 15,
        "apnews": 15,
        "ap.org": 15,
        "gettyimages": 10,
        "afp.com": 10,
        "bbc": 8,
        "cnn": 8,
        "bloomberg": 8,
        "ft.com": 8,
        "nytimes": 8,
        "wsj": 8,
        "aljazeera": 8,
        "france24": 8,
        "theguardian": 6,
        "dw.com": 6,
    }
    is_news_domain = False
    for domain, bonus in top_news_domains.items():
        if domain in lower:
            score += bonus
            is_news_domain = True
            break

    # --- WHITELIST: только новостные домены ---
    # Если домен не в списке разрешённых — отбрасываем (score = -100)
    if _NEWS_DOMAINS:
        domain_match = False
        for allowed in _NEWS_DOMAINS:
            if allowed in lower:
                domain_match = True
                break
        if not domain_match:
            # Не новостной домен — полностью отбрасываем
            return -100

    return score


def _search_images_sync(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Синхронный поиск изображений через DDGS.
    Возвращает список результатов.
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                url = r.get("image")
                if url and url.startswith(("http://", "https://")):
                    results.append(
                        {
                            "url": url,
                            "title": r.get("title", ""),
                            "source": r.get("source", ""),
                            "width": int(r.get("width", 0) or 0),
                            "height": int(r.get("height", 0) or 0),
                        }
                    )
    except Exception as e:
        logger.warning(f"⚠️ Ошибка поиска изображений для '{query[:40]}...': {e}")
    return results


def _pick_best_image(results: List[Dict[str, Any]], title: str, query: str = "") -> Optional[str]:
    """
    Выбирает лучшее изображение из списка результатов.
    Учитывает: размер, формат, релевантность URL и title.

    Фильтрует явно нерелевантные изображения (игры, несоответствие ключевым словам).
    """
    if not results:
        return None

    # Ключевые слова из заголовка и запроса для ранжирования
    title_keywords = set(re.findall(r"\b\w{3,}\b", title.lower()))
    query_keywords = set(re.findall(r"\b\w{3,}\b", query.lower()))
    all_keywords = title_keywords | query_keywords

    # Чёрный список тем, которые часто приходят в выдаче нерелевантно
    # На основе анализа 97 постов SmartNews
    _BLOCKED_TOPICS = {
        # Adult / NSFW
        "porn",
        "porno",
        "xxx",
        "adult",
        "nsfw",
        "nude",
        "naked",
        "sex",
        "sexy",
        "erotic",
        "escort",
        "onlyfans",
        "camgirl",
        "bikini",
        "lingerie",
        "fetish",
        "bdsm",
        "hentai",
        "rule34",
        # Games
        "game",
        "gaming",
        "gamer",
        "playstation",
        "xbox",
        "nintendo",
        "elden",
        "ring",
        "fortnite",
        "minecraft",
        "call of duty",
        "witcher",
        "skyrim",
        "gta",
        "grand theft auto",
        # Memes / Entertainment
        "meme",
        "funny",
        "lol",
        "joke",
        "cartoon",
        "anime",
        "wallpaper",
        "background",
        "screensaver",
        "clipart",
        "vector",
        "illustration",
        "drawing",
        "sketch",
        # Music
        "vevo",
        "music video",
        "album cover",
        "pop singer",
        # Food / Shopping
        "lindt",
        "chocolate",
        "candy",
        "sweet",
        # Education
        "methodologique",
        "guide",
        "education",
        "school",
        # Math
        "hodge",
        "conjecture",
        "mathematical",
        "topology",
        # YouTube
        "youtube",
        "youtuber",
        "video thumbnail",
    }

    scored = []
    for r in results:
        url = r["url"]
        result_title = r.get("title", "").lower()
        combined_text = f"{url.lower()} {result_title}"

        # --- ЖЁСТКИЙ ФИЛЬТР: блокируем игры, мемы и т.п. ---
        blocked = False
        for blocked_word in _BLOCKED_TOPICS:
            if blocked_word in combined_text:
                logger.debug(f"  BLOCKED (topic='{blocked_word}'): {url[:60]}...")
                blocked = True
                break
        if blocked:
            continue

        score = _score_image(url, title_keywords)

        # Бонус за размер
        width = r.get("width", 0) or 0
        height = r.get("height", 0) or 0
        if width >= 800 and height >= 600:
            score += 20
        elif width >= 400 and height >= 300:
            score += 10
        elif width > 0 and height > 0:
            score += 5

        # Штраф за слишком маленькие
        if (width > 0 and width < 200) or (height > 0 and height < 200):
            score -= 20

        # Бонус если title результата содержит ключевые слова
        for kw in all_keywords:
            if kw in result_title:
                score += 8
            if kw in url.lower():
                score += 5

        # === ПРОВЕРКА ПОЛИТИКОВ ===
        politician_patterns = {
            "trump",
            "трамп",
            "putin",
            "путин",
            "biden",
            "байден",
            "zelensky",
            "зеленский",
            "xi",
            "си",
            "цзиньпин",
            "netanyahu",
            "нетаньяху",
            "erdogan",
            "эрдоган",
            "macron",
            "макрон",
            "modi",
            "моди",
        }
        politicians_in_title = {p for p in politician_patterns if p in title.lower()}
        if politicians_in_title:
            found_politician = any(p in (url + result_title).lower() for p in politicians_in_title)
            if found_politician:
                score += 25
            else:
                score -= 40
                logger.debug(f"  PENALTY (no politician match): {url[:60]}...")

        scored.append((score, url, r))

    if not scored:
        logger.debug("🚫 Все изображения отфильтрованы по релевантности")
        return None

    # Сортируем по убыванию score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Логируем топ-3
    for i, (score, url, r) in enumerate(scored[:3]):
        logger.debug(
            f"  #{i+1} score={score} size={r.get('width')}x{r.get('height')} url={url[:60]}..."
        )

    best = scored[0]
    # Если score слишком низкий — скорее всего нерелевантно
    # Минимальный порог: 15 (раньше был 0)
    if best[0] < 25:
        logger.debug(f"🚫 Лучший результат имеет низкий score ({best[0]}), считаем нерелевантным")
        return None

    logger.info(f"🖼 Выбрано изображение (score={best[0]}): {best[1][:80]}...")
    return best[1]


async def find_news_image(article: Dict[str, Any]) -> Optional[str]:
    """
    Оркестратор поиска изображения с приоритетом:
    1. RSS/OG/HTML (extract_image_with_score)
    2. Stock API (Pixabay/Pexels/Unsplash)
    3. Скриншоты источников (Playwright)
    4. SearXNG (self-hosted)
    5. Fallback (флаг/логотип)

    Возвращает URL изображения или None.
    """
    from parsers.image_extractor import extract_image_with_score
    from utils.image_relevance_checker import get_fallback_image_url
    from utils.screenshot_generator import find_screenshot_image
    from utils.searxng_client import find_best_image
    from utils.stock_image_providers import find_best_stock_image

    title = article.get("title", "")
    summary = article.get("summary", "")
    source = article.get("source", "")
    link = article.get("link", "") or article.get("url", "")

    # Helper: проверяем, не использовалось ли изображение недавно
    def _check_image_used(url: str, source_label: str) -> bool:
        from storage.cache import cache_manager

        if cache_manager.is_image_used(url, hours=24):
            logger.info(f"🔄 Изображение уже использовалось (24h), пропускаем: {url[:60]}...")
            return True
        return False

    # === ШАГ 0: Скриншот твита (если новость про твит) ===
    try:
        from utils.tweet_screenshot import find_tweet_screenshot

        tweet_screenshot = await find_tweet_screenshot(article)
        if tweet_screenshot and not _check_image_used(tweet_screenshot, "tweet"):
            logger.info(f"📸 Скриншот твита: {tweet_screenshot[:60]}...")
            return tweet_screenshot
    except Exception as e:
        logger.debug(f"Tweet screenshot failed: {e}")

    # === ШАГ 1: RSS/OG/HTML (наивысший приоритет) ===
    if link:
        try:
            # Передаём rss_entry если есть (для извлечения RSS-нативных изображений)
            entry = article.get("rss_entry")
            result = await extract_image_with_score(entry, link, title)
            if result:
                url, score, src = result
                # Проверка на placeholder / generic изображения в RSS
                if src == "rss" and _is_rss_placeholder(url):
                    logger.info(f"🚫 RSS placeholder отклонён: {url[:60]}...")
                elif score >= 55 and not _check_image_used(
                    url, src
                ):  # OG надёжный домен или хороший RSS
                    logger.info(
                        f"🖼 RSS/OG/HTML изображение (score={score}, source={src}): {url[:60]}..."
                    )
                    return url
                elif score >= 40 and not _check_image_used(url, src):  # Article img — приемлемо
                    logger.info(f"🖼 Article image (score={score}): {url[:60]}...")
                    return url
        except Exception as e:
            logger.debug(f"RSS/OG/HTML extraction failed: {e}")

    # === ШАГ 2: Stock API ===
    try:
        stock_url = await find_best_stock_image(title, summary)
        if stock_url and not _check_image_used(stock_url, "stock"):
            logger.info(f"🖼 Stock изображение: {stock_url[:60]}...")
            return stock_url
    except Exception as e:
        logger.debug(f"Stock search failed: {e}")

    # === ШАГ 3: Скриншоты источников (новый!) ===
    try:
        screenshot_url = await find_screenshot_image(article)
        if screenshot_url and not _check_image_used(screenshot_url, "screenshot"):
            logger.info(f"📸 Скриншот источника: {screenshot_url[:60]}...")
            return screenshot_url
    except Exception as e:
        logger.debug(f"Screenshot search failed: {e}")

    # === ШАГ 4: SearXNG ===
    try:
        searx_url = await find_best_image(title, summary, max_results=10)
        if searx_url and not _check_image_used(searx_url, "searxng"):
            logger.info(f"🖼 SearXNG изображение: {searx_url[:60]}...")
            return searx_url
    except Exception as e:
        logger.debug(f"SearXNG search failed: {e}")

    # === ШАГ 5: Fallback ===
    fallback_url = get_fallback_image_url(source)
    if fallback_url and not _check_image_used(fallback_url, "fallback"):
        logger.info(f"🔄 Fallback изображение для {source}: {fallback_url[:60]}...")
        return fallback_url

    logger.info(f"🚫 Изображение не найдено для: {title[:60]}...")
    return None


def _is_rss_placeholder(url: str) -> bool:
    """Проверяет, является ли RSS-изображение placeholder'ом (логотип, generic)."""
    if not url:
        return True
    url_lower = url.lower()
    placeholder_patterns = [
        "placeholder",
        "logo",
        "default",
        "generic",
        "cover",
        "article-covers",
        "sharing",
        "og-img",
        "og_image",
        "social",
        "card",
        "preview",
        "thumb_large",
        "flagcdn",
        "cryptologos",
    ]
    return any(p in url_lower for p in placeholder_patterns)
