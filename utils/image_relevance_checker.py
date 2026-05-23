"""
Модуль проверки релевантности изображений к тексту новости.
На основе анализа 97 постов канала SmartNews.
"""

import re
from typing import Optional, Set
from urllib.parse import urlparse

# Паттерны, указывающие на НЕРЕЛЕВАНТНОЕ изображение
_IRRELEVANT_PATTERNS = {
    # Adult / NSFW
    "porn", "porno", "xxx", "adult", "nsfw", "nude", "naked",
    "sex", "sexy", "erotic", "escort", "onlyfans", "camgirl",
    "bikini", "lingerie", "fetish", "bdsm", "hentai", "rule34",
    # YouTube / Music
    "youtube.com", "ytimg.com", "youtu.be", "vevo",
    # Education / Math
    "methodologique", "guide methodologique", "oral dnb",
    "hodge conjecture", "topological cycle",
    # Music / Entertainment
    "freya skye", "pop singer", "album cover",
    # Food / Shopping
    "lindt", "chocolate", "home of chocolate",
    # Stock photos
    "alamy.com", "shutterstock.com", "dreamstime",
    # UI elements
    "favicon", "icon", "logo", "button", "badge",
    # Memes / Jokes
    "meme", "funny", "lol", "joke",
    # Games
    "game", "gaming", "playstation", "xbox", "nintendo",
    "fortnite", "minecraft", "gta", "witcher",
}

# Надежные новостные домены
_RELIABLE_DOMAINS = {
    "reuters.com", "apnews.com", "afp.com", "gettyimages.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "bloomberg.com",
    "nytimes.com", "wsj.com", "ft.com", "theguardian.com",
    "aljazeera.com", "france24.com", "dw.com",
    "ria.ru", "tass.ru", "rbc.ru", "kommersant.ru",
    "interfax.ru", "rt.com", "sputniknews.com",
    "xinhuanet.com", "scmp.com",
}


def check_image_relevance(image_url: str, title: str, summary: str = "") -> dict:
    """
    Проверяет релевантность изображения к тексту новости.
    
    Returns:
        dict: {
            'is_relevant': bool,
            'score': int,  # 0-100
            'reason': str,
            'is_absurd': bool,  # однозначно нерелевантно
        }
    """
    if not image_url:
        return {'is_relevant': False, 'score': 0, 'reason': 'No URL', 'is_absurd': False}
    
    url_lower = image_url.lower()
    text = f"{title} {summary}".lower()
    
    # 1. Проверка на абсурдные паттерны (однозначно плохие)
    for pattern in _IRRELEVANT_PATTERNS:
        if pattern in url_lower:
            return {
                'is_relevant': False,
                'score': 0,
                'reason': f'Irrelevant pattern: {pattern}',
                'is_absurd': True
            }
    
    # 2. Проверка надежности домена
    domain = urlparse(image_url).netloc.lower()
    is_reliable_domain = any(d in domain for d in _RELIABLE_DOMAINS)
    
    # 3. Извлекаем ключевые слова из текста
    text_keywords = _extract_keywords(text)
    
    # 4. Проверяем совпадение ключевых слов в URL
    url_matches = sum(1 for kw in text_keywords if kw in url_lower)
    
    # 5. Проверяем наличие имен политиков в URL
    politicians_in_text = _extract_politicians(text)
    politicians_in_url = sum(1 for p in politicians_in_text if p in url_lower)
    
    # Считаем score
    score = 0
    reasons = []
    
    if is_reliable_domain:
        score += 30
        reasons.append("Reliable domain")
    
    if url_matches > 0:
        score += url_matches * 15
        reasons.append(f"Keyword matches: {url_matches}")
    
    if politicians_in_url > 0:
        score += politicians_in_url * 25
        reasons.append(f"Politician matches: {politicians_in_url}")
    
    # Проверка на логотипы источников (нейтрально)
    if any(x in url_lower for x in ["logo", "rt.com", "coindesk", "cointelegraph"]):
        score += 10
        reasons.append("Source logo")
    
    is_relevant = score >= 40
    is_absurd = False
    
    return {
        'is_relevant': is_relevant,
        'score': min(score, 100),
        'reason': "; ".join(reasons) if reasons else "Low relevance",
        'is_absurd': is_absurd
    }


def _extract_keywords(text: str) -> Set[str]:
    """Извлекает ключевые слова из текста."""
    # Убираем стоп-слова
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were",
        "этот", "эта", "это", "как", "для", "что", "где", "когда",
        "из", "на", "в", "и", "или", "но", "за", "по", "от", "до"
    }
    
    words = re.findall(r'\b\w{4,}\b', text.lower())
    return set(w for w in words if w not in stop_words)


def _extract_politicians(text: str) -> Set[str]:
    """Извлекает имена политиков из текста."""
    politician_patterns = {
        # USA - Trump 2.0 administration
        "trump", "трамп", "vance", "вэнс", "rubio", "рубио",
        "hegseth", "хегсет", "bessent", "бессент", "waltz", "уолц",
        "leavitt", "левитт", "powell", "паулл", "greer", "грир",
        "noem", "ноэм", "bondi", "бонди", "wright", "райт",
        "lutnick", "лютник", "ratcliffe", "рэтклифф", "zeldin", "зелдин",
        "biden", "байден", "harris", "харрис", "blinken", "блинкен",
        "austin", "остин", "yellen", "йеллен",
        # Russia
        "putin", "путин", "mishustin", "мишустин", "lavrov", "лавров",
        "belousov", "белоусов", "nabiullina", "набиуллина", "shoigu", "шойгу",
        "siluanov", "силуанов", "reshetnikov", "решетников",
        # China
        "xi", "си", "jinping", "цзиньпин", "li", "ли", "chang", "чан",
        "wang", "ван", "yi", "и", "pan", "пан", "gongsheng", "гоншэн",
        # EU
        "lagarde", "лагард", "von der layen", "фон дер ляйен",
        "costa", "коста", "kalas", "каллас",
        # UK
        "starmer", "стармер", "reeves", "ривз", "lammy", "лэмми",
        "bailey", "бейли", "sunak", "сунак",
        # India
        "modi", "моди", "jaishankar", "джайшанкар", "sitharaman", "ситхараман",
        "das", "дас",
        # Ukraine
        "zelensky", "зеленский", "shmyhal", "шмыгаль", "sybiha", "сыбига",
        "umerov", "умеров", "pyshnyi", "пышный",
        # Israel
        "netanyahu", "нетаньяху", "katz", "кац", "esekal", "эсекаль",
        "smotrich", "смотрич", "yaron", "ярон",
        # Japan
        "ishiba", "ишиба", "iwaya", "ивая", "kita", "кита", "ueda", "уэда",
        # Brazil
        "lula", "лулa", "da silva", "да силва", "haddad", "аддад",
        # Other
        "lukashenko", "лукашенко", "erdogan", "эрдоган", "macron", "макрон",
        "scholz", "шольц", "trudeau", "трюдо", "kim", "ким", "jong", "чен",
        "maduro", "мадуро", "araki", "аракчи", "milei", "милей",
        "meloni", "мелони", "orban", "орбан",
    }
    
    found = set()
    text_lower = text.lower()
    for p in politician_patterns:
        if p in text_lower:
            found.add(p)
    return found


def get_fallback_image_url(source: str) -> Optional[str]:
    """
    Возвращает fallback-изображение (флаг или логотип источника),
    если поиск не нашел релевантного фото.
    """
    source_lower = source.lower()
    
    # Флаги стран для геополитических источников
    flags = {
        "rt": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Russia_flag_icon.svg/320px-Russia_flag_icon.svg.png",
        "ria": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Russia_flag_icon.svg/320px-Russia_flag_icon.svg.png",
        "tass": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Russia_flag_icon.svg/320px-Russia_flag_icon.svg.png",
        "interfax": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Russia_flag_icon.svg/320px-Russia_flag_icon.svg.png",
        "cnbc": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/Flag_of_the_United_States.svg/320px-Flag_of_the_United_States.svg.png",
        "nyt": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/Flag_of_the_United_States.svg/320px-Flag_of_the_United_States.svg.png",
        "coindesk": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Bitcoin.svg/320px-Bitcoin.svg.png",
        "cointelegraph": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Bitcoin.svg/320px-Bitcoin.svg.png",
    }
    
    for key, url in flags.items():
        if key in source_lower:
            return url
    
    return None
