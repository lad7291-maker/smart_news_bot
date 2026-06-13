"""
Единые текстовые утилиты для всего проекта.
DRY-рефакторинг: нормализация, стоп-слова, извлечение ключевых слов.
"""

import re
from typing import Set

# Объединённый набор стоп-слов из всех модулей
STOP_WORDS: Set[str] = {
    # Английские артикли и предлоги
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
    "about",
    "into",
    "than",
    "through",
    # Английские глаголы
    "is",
    "was",
    "are",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "can",
    "said",
    "says",
    "say",
    # Английские местоимения
    "this",
    "that",
    "it",
    "its",
    # Английские наречия/прилагательные
    "only",
    "other",
    "some",
    "just",
    "new",
    # Английские существительные-время
    "time",
    "year",
    "week",
    "day",
    # Русские местоимения
    "этот",
    "эта",
    "это",
    "как",
    "для",
    "что",
    "где",
    "когда",
    "кто",
    # Русские предлоги
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
    "без",
    "около",
    "против",
    "вместо",
    "вроде",
    # Русские прилагательные
    "новый",
    "новое",
    "новая",
    "новые",
    "последний",
    "последнее",
    "последняя",
    # Английские временные маркеры
    "today",
    "yesterday",
    "now",
    "latest",
    "breaking",
    "update",
    # Русские временные маркеры
    "сегодня",
    "вчера",
    "сейчас",
    "только",
    "последние",
    "экстренно",
    "срочно",
}


def normalize_title(title: str) -> str:
    """
    Нормализует заголовок для сравнения:
    - нижний регистр
    - убирает пунктуацию
    - убирает стоп-слова
    - убирает цифры (чтобы "Bitcoin упал на 5%" и "Bitcoin упал на 10%" считались дублями)
    """
    text = title.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\d+[\.,]?\d*", "", text)
    words = [w for w in text.split() if w and w not in STOP_WORDS and len(w) > 2]
    return " ".join(words)


def extract_keywords(text: str, min_length: int = 4) -> Set[str]:
    """
    Извлекает ключевые слова из текста.
    Возвращает множество слов длиной >= min_length, исключая стоп-слова.
    """
    words = re.findall(r"\b\w{" + str(min_length) + r",}\b", text.lower())
    return set(w for w in words if w not in STOP_WORDS)


def extract_keywords_heuristic(title: str, summary: str, max_words: int = 12) -> str:
    """
    Эвристический экстрактор ключевых слов.
    Используется как fallback, если AI недоступен.
    """
    text = f"{title} {summary}".strip()
    text = re.sub(r"[^\w\s\-]", " ", text)
    words = text.split()
    keywords = [w for w in words if len(w) > 2 and w.lower() not in STOP_WORDS][:max_words]
    return " ".join(keywords)


def extract_top_keywords(title: str, summary: str, max_words: int = 5) -> str:
    """
    Извлекает топ-N ключевых слов из заголовка для поиска фото.
    Приоритет отдаёт именам собственным.
    """
    text = f"{title} {summary[:200]}".strip()
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()

    keywords = []
    seen: Set[str] = set()

    # Сначала ищем имена собственные
    proper_names = re.findall(r"\b[А-ЯЁ][а-яё]+\b|\b[A-Z][a-z]+\b", title)
    for name in proper_names:
        n = name.lower()
        if n not in STOP_WORDS and len(n) > 2 and n not in seen:
            keywords.append(name)
            seen.add(n)
            if len(keywords) >= max_words:
                break

    for word in words:
        w = word.lower().strip()
        if w not in STOP_WORDS and len(w) > 3 and w not in seen:
            keywords.append(word)
            seen.add(w)
            if len(keywords) >= max_words:
                break

    return " ".join(keywords)
