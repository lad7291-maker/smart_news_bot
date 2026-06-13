"""
Модуль извлечения цитат из текста новостей.

Ищет прямую речь (кавычки, тире, "сказал", "заявил" и т.д.) в тексте статьи
и возвращает наиболее релевантную цитату для включения в пост.
"""

import re
from typing import Dict, List, Optional

# Список глаголов речи для поиска спикера
SPEECH_VERBS_RU = [
    "сказал",
    "заявил",
    "отметил",
    "подчеркнул",
    "добавил",
    "пояснил",
    "уточнил",
    "заключил",
    "заверил",
    "предупредил",
    "призвал",
    "отреагировал",
    "прокомментировал",
    "подтвердил",
    "опроверг",
    "сообщил",
    "рассказал",
    "объяснил",
    "признал",
    "утверждал",
    "заверил",
    "предупредил",
    "призвал",
    "отреагировал",
    "прокомментировал",
    "подтвердил",
    "опроверг",
    "сообщил",
    "рассказал",
    "объяснил",
    "признал",
    "утверждал",
]

SPEECH_VERBS_EN = [
    "said",
    "stated",
    "noted",
    "added",
    "emphasized",
    "clarified",
    "confirmed",
    "claimed",
    "announced",
    "declared",
    "remarked",
    "mentioned",
    "explained",
    "told",
    "warned",
    "urged",
    "acknowledged",
    "admitted",
    "asserted",
    "commented",
    "concluded",
    "insisted",
    "pointed out",
    "recalled",
    "reported",
    "stressed",
    "suggested",
    "wrote",
    "tweeted",
    "posted",
]


def extract_quotes(text: str, max_quotes: int = 3) -> List[Dict[str, str]]:
    """
    Извлекает цитаты из текста новости.

    Args:
        text: Текст статьи или summary
        max_quotes: Максимальное количество цитат для возврата

    Returns:
        Список словарей с ключами 'quote' (текст цитаты) и 'speaker' (кто сказал)
    """
    if not text or len(text) < 50:
        return []

    quotes = []

    # Паттерн 1: «Кавычки-ёлочки» — самый надёжный
    # «Текст цитаты», — сказал Иванов.
    # Используем нежадный поиск до ближайших закрывающих кавычек
    # Разрешаем до 20 символов между кавычками и тире (для точки, пробела и т.д.)
    pattern1 = re.compile(
        r'[«"]([^»"]{20,300})[»"].{0,20}[—\-–]\s*(?:\w+\s+)?(?:'
        + "|".join(SPEECH_VERBS_RU)
        + r")[аи]?\s*([^.,;]{2,60})",
        re.IGNORECASE | re.UNICODE,
    )

    # Паттерн 2: "Кавычки-лапки" с указанием автора
    pattern2 = re.compile(
        r'["\']([^"\']{20,300})["\'].{0,20}[—\-–]\s*(?:\w+\s+)?(?:'
        + "|".join(SPEECH_VERBS_RU)
        + r")[аи]?\s*([^.,;]{2,60})",
        re.IGNORECASE | re.UNICODE,
    )

    # Паттерн 3: Прямая речь после тире без кавычек
    # — Текст цитаты, — сказал Иванов.
    # Используем нежадный поиск: останавливаемся на первом тире+глаголе
    pattern3 = re.compile(
        r"[—\-–]\s*([^—\-–]{20,300}?)[\s,]*[—\-–]\s*(?:\w+\s+)?(?:"
        + "|".join(SPEECH_VERBS_RU)
        + r")[аи]?\s*([^.,;]{2,60})",
        re.IGNORECASE | re.UNICODE,
    )

    # Паттерн 4: Английские кавычки с said/stated
    pattern4 = re.compile(
        r'["""]([^"""]{20,300})["""].{0,20}[—\-–]?\s*(?:\w+\s+)?(?:'
        + "|".join(SPEECH_VERBS_EN)
        + r")?\s*([^.,;]{2,60})",
        re.IGNORECASE | re.UNICODE,
    )

    # Паттерн 5: По словам / According to
    pattern5 = re.compile(
        r'(?:По словам|Словами|Как (?:сообщил|заявил|сказал|отметил|подчеркнул|пояснил|уточнил|заключил|заверил|предупредил|призвал|отреагировал|прокомментировал|подтвердил|опроверг|рассказал|объяснил|признал|утверждал)|According to|As (?:stated|said|noted|mentioned|explained) by)\s+([^.,;]{2,60})[,:]\s*["""«"""]([^"""»]{20,300})["""»]',
        re.IGNORECASE | re.UNICODE,
    )

    for pattern in [pattern1, pattern2, pattern3, pattern4, pattern5]:
        for match in pattern.finditer(text):
            if pattern == pattern5:
                speaker = match.group(1).strip()
                quote_text = match.group(2).strip()
            else:
                quote_text = match.group(1).strip()
                speaker = match.group(2).strip() if match.lastindex >= 2 else ""

            # Очистка цитаты
            quote_text = re.sub(r"\s+", " ", quote_text)
            quote_text = quote_text.strip(".,;:!?")

            # Фильтры
            if len(quote_text) < 20 or len(quote_text) > 300:
                continue
            if _is_low_quality_quote(quote_text):
                continue
            # Проверяем, что цитата не содержит внутренние кавычки (значит захватили лишнее)
            if "«" in quote_text or '"' in quote_text[1:]:
                # Пытаемся обрезать до первой внутренней кавычки
                for quote_char in ["«", '"']:
                    if quote_char in quote_text:
                        idx = quote_text.index(quote_char)
                        if idx > 20:
                            quote_text = quote_text[:idx].strip()
                            break

            quotes.append(
                {
                    "quote": quote_text,
                    "speaker": speaker.strip() if speaker else "",
                    "length": len(quote_text),
                }
            )

    # Удаляем дубликаты и сортируем по качеству
    quotes = _deduplicate_quotes(quotes)
    quotes = _score_quotes(quotes)

    return quotes[:max_quotes]


def _is_low_quality_quote(text: str) -> bool:
    """Проверяет, является ли цитата низкокачественной."""
    # Слишком короткие
    if len(text) < 20:
        return True

    # Содержит только даты/цифры/ссылки
    if re.match(r"^[\d\s\-/.,:]+$", text):
        return True

    # Содержит HTML
    if "<" in text and ">" in text:
        return True

    # Содержит только стоп-слова
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
        "this",
        "that",
        "it",
        "its",
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
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "the",
        "a",
        "an",
    }
    words = set(text.lower().split())
    if len(words - stop_words) < 3:
        return True

    return False


def _deduplicate_quotes(quotes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Удаляет дубликаты цитат."""
    seen = set()
    unique = []
    for q in quotes:
        key = q["quote"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


def _score_quotes(quotes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Сортирует цитаты по качеству (длина, наличие спикера, содержательность)."""

    def score(q):
        s = 0
        # Длина: оптимально 80-150 символов
        length = len(q["quote"])
        if 80 <= length <= 150:
            s += 10
        elif 50 <= length <= 200:
            s += 5

        # Наличие спикера
        if q.get("speaker"):
            s += 5

        # Содержит ли имя/фамилию (вероятно, важная персона)
        if re.search(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+", q["quote"]):
            s += 3
        if re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", q["quote"]):
            s += 3

        # Содержит ли ключевые слова важности
        important_words = [
            "важно",
            "критично",
            "серьёзно",
            "необходимо",
            "обязательно",
            "невозможно",
            "недопустимо",
            "требуется",
            "призвал",
            "предупредил",
            "заявил",
            "подчеркнул",
            "important",
            "critical",
            "serious",
            "necessary",
            "must",
            "impossible",
            "unacceptable",
            "required",
            "urged",
            "warned",
            "stated",
            "emphasized",
        ]
        for word in important_words:
            if word.lower() in q["quote"].lower():
                s += 2

        return s

    quotes.sort(key=score, reverse=True)
    return quotes


def get_best_quote(text: str) -> Optional[Dict[str, str]]:
    """
    Возвращает лучшую цитату из текста или None.

    Args:
        text: Текст статьи

    Returns:
        Словарь с 'quote' и 'speaker' или None
    """
    quotes = extract_quotes(text, max_quotes=1)
    return quotes[0] if quotes else None


def format_quote_for_post(quote_data: Optional[Dict[str, str]]) -> str:
    """
    Форматирует цитату для вставки в пост.

    Args:
        quote_data: Словарь с 'quote' и 'speaker'

    Returns:
        HTML-форматированная строка цитаты или пустая строка
    """
    if not quote_data or not quote_data.get("quote"):
        return ""

    quote = quote_data["quote"]
    speaker = quote_data.get("speaker", "")

    if speaker:
        return f"\n<blockquote>«{quote}» — {speaker}.</blockquote>\n"
    else:
        return f"\n<blockquote>«{quote}»</blockquote>\n"


if __name__ == "__main__":
    # Тесты
    test_texts = [
        # Русский
        "Президент заявил: «Мы должны защитить наших граждан». — сказал он на пресс-конференции.",
        "По словам министра обороны Шойгу: «Армия готова к любым сценариям».",
        "— Мы не допустим эскалации, — заявил глава МИД Лавров.",
        # Английский
        '"The economy is recovering faster than expected," said Fed Chair Powell.',
        'According to President Biden: "We must stand with our allies."',
        # Без кавычек
        "Глава Пентагона Хегсет заявил, что будущее Кубы находится в руках президента.",
    ]

    for text in test_texts:
        print(f"\nТекст: {text[:80]}...")
        quotes = extract_quotes(text)
        for q in quotes:
            print(f"  Цитата: «{q['quote'][:80]}...»")
            print(f"  Спикер: {q['speaker']}")
