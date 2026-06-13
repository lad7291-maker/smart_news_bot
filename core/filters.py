"""
Модуль фильтрации новостей.
P1-001: Вынесен из bot_runner.py.

Фильтрует мусор, рекламные статьи, нерелевантный контент.
"""

import re
from typing import Any, Dict, List, Optional

from langdetect import LangDetectException, detect

from core.scoring import detect_score
from utils.logger import logger

# === Ключевые слова для фильтрации (базовая релевантность) ===
KEYWORDS: List[str] = [
    "политика",
    "политик",
    "путин",
    "трамп",
    "санкции",
    "выборы",
    "война",
    "финансы",
    "финансов",
    "экономика",
    "рубль",
    "доллар",
    "евро",
    "инфляция",
    "ставка",
    "крипто",
    "биткоин",
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "криптовалюта",
    "token",
    "металл",
    "золото",
    "серебро",
    "платина",
    "медь",
    "никель",
    "алюминий",
    "украина",
    "сырье",
    "сырьё",
    "нефть",
    "газ",
    "уголь",
    "пшеница",
    "кукуруза",
    "сталь",
    "руда",
    "россия",
    "сша",
    "китай",
    "европа",
    "бизнес",
    "инвестиции",
    "акции",
    "облигации",
    "форекс",
    "биржа",
    "трейдинг",
    "Moex",
    "Nasdaq 100",
]

# === BLACKLIST: мусорные заголовки ===
_JUNK_WORDS = {
    "умножить",
    "разделить",
    "сложить",
    "вычесть",
    "пример",
    "тест",
    "викторина",
    "quiz",
    "опрос",
    "голосование",
    "хохот",
    "смешно",
    "прикол",
    "анекдот",
    "мем",
    "угадай",
    "найди",
    "реши",
    "ответь",
    "загадка",
    "головоломка",
    "ребус",
    "сколько будет",
    "считай",
    "математика",
}

# === BLACKLIST: рекламные / обзорные / нативные промо-статьи ===
_AD_PATTERNS = {
    r"топ[- ]?\d+",
    r"обзор[а-я]*\s+(сервис|платформ|инструмент|программ|приложен)",
    r"подборка[а-я]*\s+(сервис|платформ|инструмент|программ|приложен)",
    r"рейтинг[а-я]*\s+(сервис|платформ|инструмент|программ|приложен|crm)",
    r"сравнен[а-я]*\s+(сервис|платформ|инструмент|программ|приложен|crm)",
    r"лучш[а-я]*\s+(сервис|платформ|инструмент|программ|приложен|crm)",
    r"как выбрать[а-я]*\s+(сервис|платформ|инструмент|программ)",
    r"как увелич[а-я]*\s+(продаж|доход|прибыл|конверси)",
    r"как повыс[а-я]*\s+(продаж|доход|прибыл|конверси)",
    r"как улучш[а-я]*\s+(продаж|доход|прибыл|конверси)",
    r"как заработ[а-я]*",
    r"как сэконом[а-я]*",
    r"гайд[а-я]*\s+по",
    r"советы?\s+по\s+(продвижен|продаж|маркетин)",
    r"инструменты?\s+для\s+(роста|продаж|маркетин)",
    r"промокод",
    r"реферальн",
    r"партнёрская\s+программ",
    r"партнерская\s+программ",
    r"купон",
    r"скидка\s+\d+",
    r"распродажа",
    r"акция\s+до",
    r"бесплатн[а-я]*\s+(доступ|период|тариф)",
    r"попробуй[а-я]*\s+бесплатно",
}


def is_russian(text: str) -> bool:
    """Проверяет, является ли текст русскоязычным."""
    if not text:
        return False
    try:
        lang = detect(text[:500])
        return lang == "ru"
    except LangDetectException:
        return bool(re.search("[а-яА-Я]", text))


def is_relevant(text: str) -> bool:
    """Проверяет релевантность текста по ключевым словам."""
    if not text:
        return False
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in KEYWORDS)


def _is_junk(text: str) -> bool:
    """Проверяет, является ли текст мусором (викторина, тест, мат. пример)."""
    text_lower = text.lower()
    for junk in _JUNK_WORDS:
        if junk in text_lower:
            return True
    return False


def _is_advertorial(title: str) -> bool:
    """Проверяет, является ли заголовок обзорной/рекламной статьёй (native ad)."""
    text_lower = title.lower()
    for pattern in _AD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def filter_article(article: Dict[str, Any], user_prefs: Optional[Dict[str, Any]] = None) -> bool:
    """
    Фильтрует новость по множеству критериев.

    Returns:
        True если статья проходит фильтр
    """
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    full_text = f"{title} {summary}"

    # Фильтр мусора
    if _is_junk(title):
        logger.debug(f"🗑 Мусор отфильтрован: {title[:60]}...")
        return False

    # Фильтр рекламных/обзорных статей
    if _is_advertorial(title):
        logger.info(f"🚫 Рекламная статья отфильтрована: {title[:80]}...")
        return False

    # Фильтр по минимальному score пользователя
    if user_prefs:
        min_score = user_prefs.get("min_score", 1)
        score = detect_score(article, user_prefs)
        if score < min_score:
            logger.debug(f"🗑 Score {score} < min_score {min_score}: {title[:60]}...")
            return False

    # Минимальная длина summary
    if summary and len(summary) < 80:
        logger.debug(f"🗑 Слишком короткий summary ({len(summary)} симв.): {title[:60]}...")
        return False

    return is_russian(full_text) and is_relevant(full_text)
