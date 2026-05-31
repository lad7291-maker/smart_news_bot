"""
Модуль семантической дедупликации новостей.
Убирает дубли одной и той же новости из разных источников.
"""

import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Set

from utils.logger import logger


def _normalize_title(title: str) -> str:
    """
    Нормализует заголовок для сравнения:
    - нижний регистр
    - убирает пунктуацию
    - убирает стоп-слова
    - убирает цифры (чтобы "Bitcoin упал на 5%" и "Bitcoin упал на 10%" считались дублями)
    """
    text = title.lower()
    # Убираем пунктуацию
    text = re.sub(r"[^\w\s]", " ", text)
    # Убираем цифры (проценты, суммы часто меняются в разных источниках)
    text = re.sub(r"\d+[\.,]?\d*", "", text)
    # Убираем стоп-слова
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
        "без",
        "около",
        "против",
        "вместо",
        "вроде",
        "вроде",
        "новый",
        "новое",
        "новая",
        "новые",
        "последний",
        "последнее",
        "последняя",
        "today",
        "yesterday",
        "now",
        "just",
        "new",
        "latest",
        "breaking",
        "update",
        "сегодня",
        "вчера",
        "сейчас",
        "только",
        "последние",
        "экстренно",
        "срочно",
    }
    words = [w for w in text.split() if w and w not in stop_words and len(w) > 2]
    return " ".join(words)


def _extract_key_entities(title: str) -> Set[str]:
    """
    Извлекает ключевые сущности из заголовка:
    - имена собственные (с заглавной буквы)
    - названия компаний (тикеры, бренды)
    - уникальные термины
    """
    words = re.findall(r"\b[A-Z][a-z]+\b|\b[A-Z]{2,6}\b", title)
    # Также добавляем русские имена собственные
    ru_proper = re.findall(r"\b[А-Я][а-я]+\b", title)
    entities = set(w.lower() for w in words + ru_proper)
    # Фильтруем короткие и общие слова
    common = {
        "the",
        "and",
        "for",
        "new",
        "now",
        "today",
        "this",
        "that",
        "with",
        "from",
        "more",
        "over",
        "after",
        "first",
        "last",
        "year",
        "week",
        "day",
        "time",
        "said",
        "says",
        "say",
        "will",
        "about",
        "into",
        "than",
        "only",
        "other",
        "some",
        "come",
        "could",
        "state",
        "still",
        "while",
        "made",
        "make",
        "well",
        "where",
        "much",
        "before",
        "right",
        "too",
        "any",
        "same",
        "tell",
        "very",
        "when",
        "much",
        "would",
        "there",
        "their",
        "what",
        "your",
        "all",
        "each",
        "which",
        "she",
        "do",
        "how",
        "if",
        "out",
        "up",
        "so",
        "can",
        "her",
        "him",
        "his",
        "has",
        "had",
        "my",
        "did",
        "get",
        "its",
        "our",
        "us",
        "may",
        "use",
        "man",
        "men",
        "way",
        "old",
        "see",
        "him",
        "two",
        "how",
        "its",
        "oil",
        "sit",
        "set",
        "run",
        "eat",
        "far",
        "sea",
        "eye",
        "ago",
        "off",
        "too",
        "old",
        "tell",
        "very",
        "when",
        "much",
        "would",
        "there",
        "their",
        "what",
        "say",
        "she",
        "each",
        "which",
        "do",
        "how",
        "if",
        "up",
        "out",
        "many",
        "then",
        "them",
        "these",
        "some",
        "her",
        "would",
        "make",
        "like",
        "into",
        "him",
        "has",
        "two",
        "more",
        "go",
        "no",
        "way",
        "could",
        "my",
        "than",
        "first",
        "been",
        "call",
        "who",
        "its",
        "now",
        "find",
        "long",
        "down",
        "day",
        "did",
        "get",
        "come",
        "made",
        "may",
        "part",
    }
    return entities - common


# Маппинг имён и терминов: русское → каноническое (английское)
_NAME_MAP = {
    # Политики
    "трамп": "trump",
    "трампа": "trump",
    "трампу": "trump",
    "байден": "biden",
    "байдена": "biden",
    "байдену": "biden",
    "путин": "putin",
    "путина": "putin",
    "путину": "putin",
    "зеленский": "zelensky",
    "зеленского": "zelensky",
    "си": "xi",
    "цзиньпин": "xi",
    "натаньяху": "netanyahu",
    "эрдоган": "erdogan",
    "макрон": "macron",
    "сун": "sunak",
    "стармер": "starmer",
    "трюдо": "trudeau",
    "моди": "modi",
    "лula": "lula",
    "мбс": "mbs",
    # Страны / регионы
    "россия": "russia",
    "рф": "russia",
    "российск": "russia",
    "сша": "usa",
    "америка": "usa",
    "американск": "usa",
    "китай": "china",
    "китая": "china",
    "китайск": "china",
    "китайский": "china",
    "китайские": "china",
    "china": "china",
    "chinese": "china",
    "кндр": "nkorea",
    "украина": "ukraine",
    "украинск": "ukraine",
    "европа": "europe",
    "европейск": "europe",
    "ес": "eu",
    "евросоюз": "eu",
    "израиль": "israel",
    "израильск": "israel",
    "иран": "iran",
    "иранск": "iran",
    "индия": "india",
    "индийск": "india",
    "япония": "japan",
    "японск": "japan",
    "германия": "germany",
    "германск": "germany",
    "франция": "france",
    "французск": "france",
    "британия": "uk",
    "великобритания": "uk",
    "британск": "uk",
    "турция": "turkey",
    "турц": "turkey",
    "бразилия": "brazil",
    "бразильск": "brazil",
    "корея": "korea",
    "корейск": "korea",
    "саудовская аравия": "saudi",
    "саудовск": "saudi",
    "оаэ": "uae",
    "канада": "canada",
    "канадск": "canada",
    "австралия": "australia",
    "австралийск": "australia",
    "швейцария": "switzerland",
    "швейцарск": "switzerland",
    # Компании / бренды
    "биткоин": "bitcoin",
    "биткойн": "bitcoin",
    "эфириум": "ethereum",
    "тесла": "tesla",
    "эпл": "apple",
    "apple": "apple",
    "гугл": "google",
    "google": "google",
    "майкрософт": "microsoft",
    "microsoft": "microsoft",
    "амазон": "amazon",
    "amazon": "amazon",
    "мета": "meta",
    "meta": "meta",
    "нвидиа": "nvidia",
    "nvidia": "nvidia",
    "опенай": "openai",
    "openai": "openai",
    "чатгпт": "chatgpt",
    "chatgpt": "chatgpt",
    "самсунг": "samsung",
    "хендай": "hyundai",
    "бинанс": "binance",
    "койнбейс": "coinbase",
    "эксон": "exxon",
    "шелл": "shell",
    "шеврон": "chevron",
    "арамко": "aramco",
    # Финансовые термины
    "ставка": "rate",
    "ставки": "rate",
    "тариф": "tariff",
    "тарифы": "tariff",
    "пошлина": "tariff",
    "пошлины": "tariff",
    "санкции": "sanction",
    "санкция": "sanction",
    "инфляция": "inflation",
    "дефолт": "default",
    "рецессия": "recession",
    "кризис": "crisis",
    "нефть": "oil",
    "газ": "gas",
    "золото": "gold",
    # Организации
    "фрс": "fed",
    "фед": "fed",
    "цб": "centralbank",
    "нато": "nato",
    "опек": "opec",
    "есб": "ecb",
}


def _canonical_name(word: str) -> str:
    """Возвращает каноническую форму слова (для сравнения across languages)."""
    w = word.lower().strip()
    return _NAME_MAP.get(w, w)


def _extract_translatable_keywords(title: str) -> Set[str]:
    """
    Извлекает ключевые слова, которые часто переводятся по-разному,
    но обозначают одно и то же (имена, названия компаний, тикеры).
    """
    text = title.lower()
    keywords = set()

    # Имена людей / компаний / стран (с канонизацией)
    # Ищем в оригинальном title — имена собственные с заглавной буквы
    names = re.findall(r"\b[А-ЯЁ][а-яё]+\b|\b[A-Z][a-z]+\b", title)
    for name in names:
        n = name.lower()
        if len(n) > 2 and n not in {
            "the",
            "and",
            "for",
            "new",
            "now",
            "today",
            "this",
            "that",
            "with",
            "from",
            "more",
            "over",
            "after",
            "first",
            "last",
            "year",
            "week",
            "day",
            "time",
            "said",
            "says",
            "say",
            "will",
            "about",
            "into",
            "than",
            "only",
            "other",
        }:
            keywords.add(_canonical_name(n))

    # Также ищем многословные термины (например, "саудовская аравия", "south korea")
    for ru_term, canonical in _NAME_MAP.items():
        if " " in ru_term and ru_term in text:
            keywords.add(canonical)
        elif " " not in ru_term and ru_term in text.split():
            keywords.add(canonical)

    # Тикеры / аббревиатуры (2-6 заглавных букв)
    tickers = re.findall(r"\b[A-Z]{2,6}\b", title)
    for t in tickers:
        keywords.add(t.lower())

    # Числовые значения (ставки, проценты — часто одинаковые в разных источниках)
    numbers = re.findall(r"\d+[\.,]?\d*", text)
    for num in numbers:
        keywords.add(num.replace(",", "."))

    return keywords


def _title_similarity(a: str, b: str) -> float:
    """
    Вычисляет схожесть двух заголовков (0.0 - 1.0).
    Учитывает:
    - Нормализованные заголовки (для одноязычных)
    - Ключевые сущности (имена, тикеры)
    - Переводимые ключевые слова (для многоязычных)
    """
    norm_a = _normalize_title(a)
    norm_b = _normalize_title(b)

    if not norm_a or not norm_b:
        return 0.0

    # Быстрая проверка: если нормализованные заголовки совпадают — это дубль
    if norm_a == norm_b:
        return 1.0

    # SequenceMatcher для fuzzy matching (одноязычных)
    base_sim = SequenceMatcher(None, norm_a, norm_b).ratio()

    # --- Проверка ключевых сущностей (имена, тикеры) с канонизацией ---
    entities_a = {_canonical_name(e) for e in _extract_key_entities(a)}
    entities_b = {_canonical_name(e) for e in _extract_key_entities(b)}
    entity_sim = 0.0
    if entities_a and entities_b:
        common = entities_a & entities_b
        union = entities_a | entities_b
        entity_sim = len(common) / len(union) if union else 0

    # --- Проверка переводимых ключевых слов (для разных языков) ---
    trans_a = _extract_translatable_keywords(a)
    trans_b = _extract_translatable_keywords(b)
    trans_sim = 0.0
    if trans_a and trans_b:
        common = trans_a & trans_b
        union = trans_a | trans_b
        trans_sim = len(common) / len(union) if union else 0

    # --- Специальная логика для многоязычных дублей ---
    # Объединяем entities и translatable keywords для полной картины
    all_keywords_a = entities_a | trans_a
    all_keywords_b = entities_b | trans_b
    common_all = all_keywords_a & all_keywords_b
    common_names = entities_a & entities_b
    common_numbers = trans_a & trans_b
    has_numbers = bool(re.search(r"\d", a)) and bool(re.search(r"\d", b))

    # Сильный сигнал: 2+ общих ключевых слова (имена/страны/компании) = точно дубль
    if len(common_names) >= 2:
        return max(base_sim, 0.92)

    # Средний сигнал: 2+ общих ключевых слова в объединённом наборе
    if len(common_all) >= 2:
        return max(base_sim, 0.88)

    # Слабый сигнал: 1 общее ключевое слово + общие цифры
    if len(common_all) >= 1 and has_numbers and len(common_numbers) >= 1:
        return max(base_sim, 0.85)

    # Если много общих ключевых слов на разных языках + похожие цифры
    if trans_sim >= 0.5 and has_numbers and len(common_numbers) >= 1:
        return max(base_sim, 0.82)

    # Стандартная формула для одноязычных
    return base_sim * 0.5 + entity_sim * 0.3 + trans_sim * 0.2


def deduplicate_articles(
    articles: List[Dict[str, Any]], similarity_threshold: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Убирает дублирующиеся новости из списка.

    Алгоритм:
    1. Сортирует по score (высокий первым) и свежести
    2. Для каждой новости проверяет, нет ли похожей уже в результате
    3. Если похожая найдена (similarity >= threshold) — пропускает

    Возвращает список уникальных новостей.
    """
    if not articles:
        return []

    # Сортируем: сначала высокий score, потом свежесть
    sorted_articles = sorted(
        articles,
        key=lambda x: (x.get("score", 0), x.get("published") or datetime.now()),
        reverse=True,
    )

    unique = []
    skipped = 0

    # Topic cooldown: если тема (сущности) уже была в последние 6 часов — пропускаем
    _topic_history = []  # [(entities_set, timestamp), ...]
    TOPIC_COOLDOWN_HOURS = 6

    for article in sorted_articles:
        title = article.get("title", "")
        if not title:
            continue

        # === TOPIC COOLDOWN ===
        article_entities = {_canonical_name(e) for e in _extract_key_entities(title)}
        article_time = article.get("published") or datetime.now()
        if article_time and isinstance(article_time, datetime):
            cooldown_cutoff = article_time - timedelta(hours=TOPIC_COOLDOWN_HOURS)
            for past_entities, past_time in _topic_history:
                if past_time > cooldown_cutoff:
                    # Если 2+ общих сущностей — считаем той же темой
                    common_entities = article_entities & past_entities
                    if len(common_entities) >= 2:
                        logger.info(
                            f"⏳ Topic cooldown (6h): '{title[:60]}...' — та же тема, пропускаем"
                        )
                        skipped += 1
                        break
            else:
                _topic_history.append((article_entities, article_time))
                # Очищаем старые записи
                _topic_history = [(e, t) for e, t in _topic_history if t > cooldown_cutoff]

        is_duplicate = False
        for existing in unique:
            existing_title = existing.get("title", "")
            sim = _title_similarity(title, existing_title)
            if sim >= similarity_threshold:
                logger.debug(
                    f"🔄 Дубль удалён (sim={sim:.2f}): '{title[:60]}...' "
                    f"→ похож на '{existing_title[:60]}...' [{existing.get('source')} vs {article.get('source')}]"
                )
                is_duplicate = True
                skipped += 1
                break

        if not is_duplicate:
            unique.append(article)

    if skipped > 0:
        logger.info(f"🔄 Дедупликация: убрано {skipped} дублей, осталось {len(unique)} уникальных")
    else:
        logger.info(f"🔄 Дедупликация: дублей не найдено ({len(unique)} новостей)")

    return unique
