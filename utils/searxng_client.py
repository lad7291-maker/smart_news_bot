"""
Клиент для self-hosted SearXNG — поиск изображений.

SearXNG запущен через Docker на localhost:8888.
Используется как 3-й приоритет после RSS/OG.
P1-002: Переписан на httpx.AsyncClient для неблокирующего async ввода-вывода.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from config import config
from utils.text_utils import extract_keywords, extract_top_keywords

# Простая нормализация русских слов (удаление окончаний)
_RUSSIAN_SUFFIXES = [
    # Существительные (родительный/дательный/винительный/творительный/предложный)
    "ом",
    "ем",
    "ам",
    "ям",
    "ах",
    "ях",
    "ов",
    "ев",
    "ей",
    "ий",
    "ый",
    "ой",
    "ью",
    "ью",
    "ом",
    "ем",
    "ам",
    "ям",
    "ах",
    "ях",
    "ии",
    "ии",
    "ия",
    "ию",
    "ией",
    "иею",  # молдавии, россии
    "авии",
    "авия",
    "авию",  # молдавии
    "ании",
    "ания",
    "анию",  # германии
    "ении",
    "ения",
    "ению",  # прекращении
    "ении",
    "ения",
    "ению",  # соглашении
    "ости",
    "ость",
    "остью",  # новости
    "еств",
    "ества",
    "еству",  # евросоюз - нет
    "ез",
    "еза",
    "езу",  # газ -> нет
    "и",
    "у",
    "е",
    "ой",
    "ю",
    "а",
    "ы",  # короткие окончания
    # Глаголы
    "ет",
    "ут",
    "ют",
    "ит",
    "ат",
    "ят",
    "ил",
    "ел",
    "ал",
    "ул",
    "ыл",
    "ают",
    "яют",
    "ает",
    "яет",
    "или",
    "ели",
    "али",
    "ули",
    "ыли",
    # Прилагательные
    "ого",
    "его",
    "ому",
    "ему",
    "ими",
    "ыми",
    "ом",
    "ем",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
]


def _normalize_word(word: str) -> str:
    """Нормализует слово для лучшего сопоставления."""
    word = word.lower().strip()
    # Удаляем русские окончания
    for suffix in _RUSSIAN_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


logger = logging.getLogger(__name__)

# Нежелательные паттерны в URL изображений
_BAD_PATTERNS = {
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
    "porn",
    "porno",
    "xxx",
    "adult",
    "nsfw",
    "nude",
}

# Предпочтительные расширения
_GOOD_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Нерелевантные темы, которые часто приходят в выдаче
_BLOCKED_TOPICS = {
    # Животные / природа (когда новость не про это)
    "bird",
    "birds",
    "seagull",
    "pigeon",
    "duck",
    "goose",
    "beach",
    "ocean",
    "sea",
    "sand",
    "sunset",
    "sunrise",
    "mountain",
    "forest",
    "tree",
    "flower",
    "garden",
    # Еда
    "food",
    "meal",
    "dish",
    "restaurant",
    "cafe",
    # Спорт (если не спортивная новость)
    "football",
    "soccer",
    "basketball",
    "tennis",
    "golf",
    # Мемы / развлечения
    "meme",
    "funny",
    "lol",
    "joke",
    "cartoon",
    "anime",
    "wallpaper",
    "background",
    "clipart",
    "vector",
    # Музыка / видео
    "vevo",
    "music",
    "album",
    "concert",
    "festival",
    # Образование / наука (абстрактное)
    "education",
    "school",
    "university",
    "student",
    "mathematical",
    "topology",
    "equation",
    "formula",
}


# Транслитерация: русское слово -> английское
_TRANSLIT_MAP = {
    "израил": "israel",
    "ливан": "lebanon",
    "иран": "iran",
    "ирак": "iraq",
    "сирия": "syria",
    "украин": "ukraine",
    "росси": "russia",
    "кита": "china",
    "герман": "germany",
    "франц": "france",
    "турц": "turkey",
    "инди": "india",
    "япон": "japan",
    "бразил": "brazil",
    "палестин": "palestine",
    "сша": "usa",
    "нато": "nato",
    "ес": "eu",
    "фрс": "fed",
    "фрг": "frg",
    "герман": "germany",
    "биткоин": "bitcoin",
    "эфириум": "ethereum",
    "крипто": "crypto",
    "трамп": "trump",
    "байден": "biden",
    "путин": "putin",
    "зеленск": "zelensky",
    "нетаньяху": "netanyahu",
    "макрон": "macron",
    "шольц": "scholz",
    "эрдоган": "erdogan",
    "си": "xi",
    "цзиньпин": "jinping",
    "моди": "modi",
    "лукашенко": "lukashenko",
    "мадуро": "maduro",
    "ким": "kim",
    "милей": "milei",
    "мелони": "meloni",
    "орбан": "orban",
    "стармер": "starmer",
    "трюдо": "trudeau",
    "лагард": "lagarde",
    "бессент": "bessent",
    "рубио": "rubio",
    "лавров": "lavrov",
    "шойгу": "shoigu",
    "набиуллина": "nabiullina",
    # Дополнительные страны и регионы
    "молдав": "moldova",
    "молдов": "moldova",
    "кишинев": "chisinau",
    "евросоюз": "eu",
    "европ": "europe",
    "польш": "poland",
    "чех": "czech",
    "венгр": "hungary",
    "румын": "romania",
    "болгар": "bulgaria",
    "словак": "slovakia",
    "хорват": "croatia",
    "серб": "serbia",
    "черногор": "montenegro",
    "словен": "slovenia",
    "прибалт": "baltic",
    "эстон": "estonia",
    "латв": "latvia",
    "литв": "lithuania",
    "финл": "finland",
    "швед": "sweden",
    "норвег": "norway",
    "дан": "denmark",
    "нидерланд": "netherlands",
    "бельг": "belgium",
    "австр": "austria",
    "швейцар": "switzerland",
    "испан": "spain",
    "португал": "portugal",
    "итал": "italy",
    "грец": "greece",
    "кипр": "cyprus",
    "малт": "malta",
    "люксембург": "luxembourg",
    "ирланд": "ireland",
    "великобритан": "britain",
    "англ": "england",
    "шотланд": "scotland",
    "уэльс": "wales",
    "коре": "korea",
    "вьетнам": "vietnam",
    "тайланд": "thailand",
    "индонез": "indonesia",
    "малайз": "malaysia",
    "филиппин": "philippines",
    "австрал": "australia",
    "канад": "canada",
    "мексик": "mexico",
    "аргентин": "argentina",
    "чил": "chile",
    "колумб": "colombia",
    "перу": "peru",
    "венесуэл": "venezuela",
    "эквадор": "ecuador",
    "уругвай": "uruguay",
    "парагвай": "paraguay",
    "болив": "bolivia",
    "куб": "cuba",
    "никарагуа": "nicaragua",
    "гондурас": "honduras",
    "гватемал": "guatemala",
    "сальвадор": "salvador",
    "панам": "panama",
    "доминикан": "dominican",
    "гаит": "haiti",
    "ямайк": "jamaica",
    "египет": "egypt",
    "саудовск": "saudi",
    "оаэ": "uae",
    "катар": "qatar",
    "кувейт": "kuwait",
    "бахрейн": "bahrain",
    "оман": "oman",
    "йемен": "yemen",
    "иордан": "jordan",
    "ливи": "libya",
    "тунис": "tunisia",
    "алжир": "algeria",
    "марокк": "morocco",
    "судан": "sudan",
    "эфиоп": "ethiopia",
    "кения": "kenya",
    "танзан": "tanzania",
    "уганд": "uganda",
    "конго": "congo",
    "замб": "zambia",
    "зимбабв": "zimbabwe",
    "ботсван": "botswana",
    "намиб": "namibia",
    "ангол": "angola",
    "мозамбик": "mozambique",
    "мадагаскар": "madagascar",
    "гвине": "guinea",
    "сеньегал": "senegal",
    "мал": "mali",
    "ган": "ghana",
    "того": "togo",
    "бенин": "benin",
    "нигер": "niger",
    "чад": "chad",
    "камерун": "cameroon",
    "габон": "gabon",
    "пакистан": "pakistan",
    "бангладеш": "bangladesh",
    "шри-ланк": "lanka",
    "непал": "nepal",
    "бутан": "bhutan",
    "мьянм": "myanmar",
    "камбодж": "cambodia",
    "лаос": "laos",
    "сингапур": "singapore",
    "бруней": "brunei",
    "монгол": "mongolia",
    "казахст": "kazakhstan",
    "узбекист": "uzbekistan",
    "туркмен": "turkmenistan",
    "киргиз": "kyrgyzstan",
    "таджикист": "tajikistan",
    "азербайджан": "azerbaijan",
    "армян": "armenia",
    "груз": "georgia",
}

# Важные имена/сущности, которые должны присутствовать в результате

# Финансовые темы — для поиска графиков вместо generic news images
_FINANCIAL_KEYWORDS = {
    # Commodities
    "нефть",
    "бrent",
    "brent",
    "wti",
    "gas",
    "газ",
    "уран",
    "uranium",
    "золото",
    "gold",
    "серебро",
    "silver",
    "медь",
    "copper",
    "алюминий",
    "aluminum",
    "палладий",
    "palladium",
    "платина",
    "platinum",
    "никель",
    "nickel",
    "металл",
    "metal",
    "commodity",
    "commodities",
    "сырье",
    # Stocks / indices
    "акци",
    "stock",
    "index",
    "индекс",
    "s&p",
    "nasdaq",
    "dow",
    "dow jones",
    "moex",
    "ртс",
    "rts",
    "фондовый",
    "фондовая",
    "биржа",
    "exchange",
    # Forex
    "рубль",
    "ruble",
    "dollar",
    "доллар",
    "евро",
    "euro",
    "yuan",
    "юань",
    "forex",
    "валют",
    "currency",
    "курс",
    # Crypto
    "биткоин",
    "bitcoin",
    "btc",
    "эфириум",
    "ethereum",
    "eth",
    "крипто",
    "crypto",
    "blockchain",
    "блокчейн",
    "токен",
    "token",
    "altcoin",
    "альткоин",
    # Economics
    "инфляц",
    "inflation",
    "дефляц",
    "deflation",
    "рецессия",
    "recession",
    "gdp",
    "ввп",
    "экономик",
    "economy",
    "экономическ",
    "economic",
    "цб",
    "центробанк",
    "central bank",
    "фрс",
    "fed",
    "ставка",
    "rate",
    # Markets
    "рынок",
    "market",
    "трейдинг",
    "trading",
    "инвестиции",
    "investment",
    "портфель",
    "portfolio",
    "брокер",
    "broker",
    "dividend",
    "дивиденд",
}

# Финансовые графиковые источники (бонус в скоринге)
_CHART_DOMAINS = {
    "investing.com",
    "tradingview.com",
    "tradingeconomics.com",
    "coingecko.com",
    "coinmarketcap.com",
    "cryptocompare.com",
    "marketwatch.com",
    "bloomberg.com",
    "reuters.com",
    "finviz.com",
    "stockcharts.com",
    "chartink.com",
}


def _is_financial_topic(title: str, summary: str = "") -> bool:
    """Определяет, является ли новость финансовой/экономической."""
    text_lower = f"{title} {summary}".lower()
    for kw in _FINANCIAL_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def _build_chart_query(title: str, summary: str) -> str:
    """Формирует запрос для поиска финансовых графиков."""
    keywords = extract_top_keywords(title, summary, max_words=4)
    # chart + price + asset + timeframe (если есть)
    query = f"{keywords} price chart"
    # Если упоминается конкретный актив — добавляем его явно
    text_lower = f"{title} {summary}".lower()
    if "brent" in text_lower or "бrent" in text_lower or "нефть brent" in text_lower:
        query = "brent crude oil price chart"
    elif "wti" in text_lower:
        query = "wti crude oil price chart"
    elif "bitcoin" in text_lower or "биткоин" in text_lower:
        query = "bitcoin btc price chart"
    elif "ethereum" in text_lower or "эфириум" in text_lower:
        query = "ethereum eth price chart"
    elif "gold" in text_lower or "золото" in text_lower:
        query = "gold price chart"
    elif "nasdaq" in text_lower:
        query = "nasdaq index chart"
    elif "s&p" in text_lower or "sp500" in text_lower or "s&p 500" in text_lower:
        query = "s&p 500 index chart"
    elif "dow" in text_lower or "dow jones" in text_lower:
        query = "dow jones index chart"
    elif "rub" in text_lower or "рубль" in text_lower or "ruble" in text_lower:
        query = "usd rub exchange rate chart"
    elif "euro" in text_lower or "евро" in text_lower:
        query = "eur usd exchange rate chart"
    elif "yu" in text_lower or "юань" in text_lower or "yuan" in text_lower:
        query = "usd cny exchange rate chart"
    elif "gas" in text_lower or "газ" in text_lower:
        query = "natural gas price chart"

    if len(query) > 100:
        query = query[:100].rsplit(" ", 1)[0] + " chart"
    return query


_IMPORTANT_NAMES = {
    # Политики
    "trump",
    "трамп",
    "biden",
    "байден",
    "putin",
    "путин",
    "zelensky",
    "зеленский",
    "netanyahu",
    "нетаньяху",
    "macron",
    "макрон",
    "scholz",
    "шольц",
    "erdogan",
    "эрдоган",
    "xi",
    "си",
    "jinping",
    "цзиньпин",
    "modi",
    "моди",
    "lula",
    "лулa",
    "milei",
    "милей",
    "orban",
    "орбан",
    "meloni",
    "мелони",
    "starmer",
    "стармер",
    "trudeau",
    "трюдо",
    "lukashenko",
    "лукашенко",
    "maduro",
    "мадуро",
    "kim",
    "ким",
    "jong",
    "чен",
    # Страны / регионы
    "israel",
    "израил",
    "palestine",
    "палестин",
    "iran",
    "иран",
    "iraq",
    "ирак",
    "syria",
    "сирия",
    "lebanon",
    "ливан",
    "ukraine",
    "украин",
    "russia",
    "росси",
    "china",
    "кита",
    "usa",
    "сша",
    "germany",
    "герман",
    "france",
    "франц",
    "turkey",
    "турц",
    "india",
    "инди",
    "japan",
    "япон",
    "brazil",
    "бразил",
    # Организации
    "nato",
    "нато",
    "eu",
    "ес",
    "opec",
    "опек",
    "wto",
    "вто",
    "un",
    "оон",
    "fed",
    "фрс",
    "ecb",
    "ецб",
    "imf",
    "мвф",
    "frg",
    "фрг",
    # Крипто
    "bitcoin",
    "биткоин",
    "ethereum",
    "эфириум",
    "crypto",
    "крипто",
}


def _extract_important_names(title: str) -> set:
    """Извлекает важные имена/сущности из заголовка."""
    title_lower = title.lower()
    found = set()
    for name in _IMPORTANT_NAMES:
        if name in title_lower:
            found.add(name)
    return found


def _build_query(title: str, summary: str) -> str:
    """Формирует поисковый запрос из полного заголовка и summary.

    P3-004: Используем полный заголовок + summary для лучшей релевантности.
    """
    # P3-003: Для финансовых новостей ищем графики вместо generic news images
    if _is_financial_topic(title, summary):
        query = _build_chart_query(title, summary)
        logger.info(f"📊 Финансовая тема — поиск графика: {query[:80]}...")
        return query

    # Используем полный заголовок + summary (первые 200 символов)
    full_text = f"{title} {summary}".strip()
    # Убираем лишние пробелы и ограничиваем длину
    full_text = " ".join(full_text.split())
    if len(full_text) > 200:
        full_text = full_text[:200].rsplit(" ", 1)[0]

    query = f"{full_text} news"
    if len(query) > 250:
        query = query[:250].rsplit(" ", 1)[0] + " news"
    return query


def _score_image_result(result: Dict[str, Any], title_keywords: set, title: str = "") -> int:
    """Оценивает качество результата изображения."""
    score = 0
    img_url = (result.get("img_src") or result.get("thumbnail_src") or "").lower()
    result_title = (result.get("title") or "").lower()

    if not img_url.startswith(("http://", "https://", "//")):
        return -100
    # Добавляем https: для protocol-relative URLs
    if img_url.startswith("//"):
        img_url = "https:" + img_url

    # Штраф за плохие паттерны
    for bad in _BAD_PATTERNS:
        if bad in img_url:
            return -100

    # Бонус за хорошие расширения
    if any(img_url.endswith(ext) for ext in _GOOD_EXTENSIONS):
        score += 10

    # --- ПРОВЕРКА РЕЛЕВАНТНОСТИ: ключевые слова должны быть в URL или title ---
    text_lower = f"{img_url} {result_title}"

    # Проверяем, есть ли ключевые слова из заголовка новости в результате
    keyword_matches = 0
    for kw in title_keywords:
        kw_lower = kw.lower()
        # Прямое совпадение
        if kw_lower in text_lower:
            keyword_matches += 1
            continue
        # Проверяем нормализованную форму (для русских падежей)
        kw_norm = _normalize_word(kw)
        if kw_norm in text_lower:
            keyword_matches += 1
            continue
        # Проверяем, есть ли нормализованное слово в нормализованном тексте
        text_normalized = " ".join(_normalize_word(w) for w in text_lower.split())
        if kw_norm in text_normalized:
            keyword_matches += 1
            continue
        # Проверяем английские варианты через транслитерацию
        kw_norm = _normalize_word(kw)
        if kw_norm in _TRANSLIT_MAP:
            eng_variant = _TRANSLIT_MAP[kw_norm]
            if eng_variant in text_lower:
                keyword_matches += 1
                continue
            # Специальные случаи
            if kw_norm == "фрг" and "germany" in text_lower:
                keyword_matches += 1
                continue

    if keyword_matches >= 2:
        score += keyword_matches * 20
    elif keyword_matches == 1:
        # Только 1 совпадение — слабый сигнал, но не отбрасываем
        score += 5
    else:
        # Ни одного ключевого слова не найдено — скорее всего нерелевантно
        return -100

    # --- ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: имена политиков и ключевых фигур ---
    # Если в заголовке есть имя политика/страны — оно ДОЛЖНО быть в результате
    important_names = _extract_important_names(title)
    if important_names:
        name_matches = 0
        for name in important_names:
            if name in text_lower:
                name_matches += 1
            elif _normalize_word(name) in text_lower:
                name_matches += 1
            elif name in _TRANSLIT_MAP and _TRANSLIT_MAP[name] in text_lower:
                name_matches += 1
            # Специальные случаи: ФРГ -> Germany
            elif name == "фрг" and "germany" in text_lower:
                name_matches += 1
        if name_matches == 0:
            # Имя политика в заголовке, но не в результате — скорее всего нерелевантно
            logger.debug(f"  SearXNG: имя политика не найдено в результате {img_url[:60]}...")
            return -100
        score += name_matches * 25

    # --- БЛОКИРОВКА НЕРЕЛЕВАНТНЫХ ТЕМ ---
    # Если новость про политику/войну, а результат про птиц/пляж — отбрасываем
    blocked_topic_found = False
    for blocked in _BLOCKED_TOPICS:
        if blocked in result_title:
            # Проверяем, упоминается ли эта тема в заголовке новости
            if blocked not in title.lower():
                logger.debug(f"  SearXNG BLOCKED (topic='{blocked}'): {img_url[:60]}...")
                blocked_topic_found = True
                break
    if blocked_topic_found:
        return -100

    # Бонус за размер (если указан)
    width = (
        result.get("resolution", "").split("x")[0]
        if "x" in str(result.get("resolution", ""))
        else ""
    )
    if width and width.isdigit() and int(width) >= 400:
        score += 10

    # P3-003: Бонус за графиковые/финансовые источники
    for chart_domain in _CHART_DOMAINS:
        if chart_domain in img_url:
            score += 15
            break

    # P3-003: Бонус если в title результата есть "chart" или "price"
    if "chart" in result_title or "price" in result_title or "график" in result_title:
        score += 10

    return score


# Мусорные домены, которые часто попадают в выдачу SearXNG
_JUNK_DOMAINS = {
    "afftimes.com",
    "bloknot.ru",
    "uimg.pravda.com.ua",
    "i.obozrevatel.com",
    "artic.edu",
    "haqqin.az",
    "gijn.org",
    "habr.com/share",
    "cdn.jsdelivr.net",  # devicons, lucide-static иконки
    "cdnn21.img.ria.ru/images/sharing",  # sharing-картинки РИА с watermark
    "img.ria.ru/images/sharing",  # sharing-картинки РИА
    "watermark",
    "gettyimages",
    "shutterstock",
    "istockphoto",
    "alamy",
    "depositphotos",
    "dreamstime",
    "123rf",
    "vectorstock",
    "canstockphoto",
    "turbosquid",
    "pond5",
    "storyblocks",
    "videoblocks",
    "motionelements",
    "logo",
    "watermarked",
    "preview",
    "sample",
    "template",
}


def _is_junk_domain(url: str) -> bool:
    """Проверяет, является ли URL мусорным доменом."""
    if not url:
        return True
    url_lower = url.lower()
    for junk in _JUNK_DOMAINS:
        if junk in url_lower:
            return True
    return False


async def search_images(
    query: str,
    max_results: int = 5,
    timeout: float = 15.0,
    retries: int = 3,
) -> List[Dict[str, Any]]:
    """
    Ищет изображения через SearXNG (async) с retry.
    JSON API для images часто пуст — добавлен HTML fallback.

    Args:
        query: Поисковый запрос
        max_results: Максимальное количество результатов
        timeout: Таймаут запроса в секундах
        retries: Количество повторных попыток

    Returns:
        Список результатов с ключами img_src, url, title и др.
    """
    searxng_url = getattr(config, "SEARXNG_URL", "http://localhost:8888")
    url = f"{searxng_url}/search"

    params_json = {
        "q": query,
        "categories": "images",
        "language": "en-US",
        "format": "json",
        "engines": "bing_images,google_images,duckduckgo_images,qwant_images,yandex_images,brave,wikimedia_image,flickr,pexels,pixabay,unsplash",
    }
    params_html = {
        "q": query,
        "categories": "images",
        "language": "en-US",
    }

    headers = {
        "User-Agent": config.USER_AGENT,
    }

    for attempt in range(retries):
        try:
            logger.debug(f"🔍 SearXNG (попытка {attempt + 1}/{retries}): {query[:60]}")
            async with httpx.AsyncClient(timeout=timeout) as client:
                # 1. Пробуем JSON
                resp = await client.get(
                    url, params=params_json, headers={**headers, "Accept": "application/json"}
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                # Фильтруем мусорные домены
                clean_results = [
                    r
                    for r in results
                    if not _is_junk_domain(r.get("img_src") or r.get("thumbnail_src") or "")
                ]
                # 2. Если JSON пустой — пробуем HTML fallback
                if not clean_results:
                    logger.debug("🔍 SearXNG JSON пуст, пробуем HTML fallback...")
                    resp_html = await client.get(url, params=params_html, headers=headers)
                    resp_html.raise_for_status()
                    soup = BeautifulSoup(resp_html.text, "html.parser")
                    html_results = []
                    for img_tag in soup.find_all("img", class_="thumbnail"):
                        src = img_tag.get("src", "")
                        if "/image_proxy" in src:
                            # image_proxy URL — прокси SearXNG, можно использовать
                            # Декодируем исходный URL из параметра
                            from urllib.parse import parse_qs, unquote

                            parsed = parse_qs(src.split("?")[1]) if "?" in src else {}
                            original_url = parsed.get("url", [src])[0]
                            # Родительский article — для title
                            article = img_tag.find_parent("article", class_="result")
                            title_link = article.find("a", rel="noreferrer") if article else None
                            title = title_link.get_text(strip=True) if title_link else ""
                            page_url = title_link.get("href", "") if title_link else ""
                            html_results.append(
                                {
                                    "img_src": (
                                        unquote(original_url)
                                        if original_url.startswith("http")
                                        else searxng_url + src
                                    ),
                                    "thumbnail_src": searxng_url + src,
                                    "url": page_url,
                                    "title": title,
                                    "engine": "searxng_image_proxy",
                                }
                            )
                    clean_results = [
                        r for r in html_results if not _is_junk_domain(r.get("img_src") or "")
                    ]
                    logger.debug(f"🔍 SearXNG HTML fallback: {len(clean_results)} результатов")

                if len(clean_results) < len(results):
                    logger.debug(
                        f"🚫 Отфильтровано {len(results) - len(clean_results)} мусорных результатов"
                    )
                logger.debug(f"🔍 SearXNG вернул {len(clean_results)} результатов")
                return clean_results[:max_results]

        except httpx.ConnectError:
            logger.warning(f"⚠️ SearXNG недоступен ({searxng_url}), попытка {attempt + 1}/{retries}")
        except httpx.TimeoutException:
            logger.warning(f"⏱ SearXNG таймаут ({timeout}s), попытка {attempt + 1}/{retries}")
        except Exception as e:
            logger.warning(f"⚠️ SearXNG ошибка: {e}, попытка {attempt + 1}/{retries}")

        if attempt < retries - 1:
            delay = 2**attempt  # Экспоненциальная задержка: 1s, 2s, 4s
            logger.info(f"⏳ Повторная попытка SearXNG через {delay}s...")
            import asyncio

            await asyncio.sleep(delay)

    return []


async def find_best_image(
    title: str,
    summary: str = "",
    max_results: int = 5,
) -> Optional[str]:
    """
    Ищет лучшее изображение для новости через SearXNG (async).

    Args:
        title: Заголовок новости
        summary: Краткое содержание
        max_results: Сколько результатов запрашивать

    Returns:
        URL лучшего изображения или None
    """
    query = _build_query(title, summary)
    results = await search_images(query, max_results=max_results)

    if not results:
        return None

    # Используем extract_keywords для лучшей нормализации
    title_keywords = extract_keywords(f"{title} {summary}", min_length=4)
    # Также добавляем английские варианты (для mixed-language matching)
    title_keywords_lower = {kw.lower() for kw in title_keywords}

    scored = []
    for r in results:
        img_url = r.get("img_src") or r.get("thumbnail_src")
        if not img_url:
            continue

        score = _score_image_result(r, title_keywords, title)
        if score > -50:  # Не совсем провальные
            scored.append((score, img_url, r))

    if not scored:
        logger.debug("🚫 SearXNG: все результаты отфильтрованы по релевантности")
        return None

    scored.sort(key=lambda x: x[0], reverse=True)

    best = scored[0]
    # Минимальный порог релевантности — только качественные результаты
    if best[0] < 50:
        logger.debug(
            f"🚫 SearXNG: лучший результат имеет низкий score ({best[0]}), считаем нерелевантным"
        )
        return None

    logger.info(f"🖼 SearXNG выбрал (score={best[0]}): {best[1][:80]}...")
    return best[1]
