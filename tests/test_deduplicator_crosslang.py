"""
Tests for cross-language deduplication (P1-005).
Проверяет обнаружение дублей на разных языках.
"""

import pytest

from utils.deduplicator import _title_similarity, deduplicate_articles


class TestCrossLanguageDeduplication:
    """Кросс-язычная дедупликация."""

    def test_same_english_title_high_similarity(self):
        """Одинаковые английские заголовки — высокая схожесть."""
        a = "Trump meets Putin in Moscow"
        b = "Trump meets Putin in Moscow"
        sim = _title_similarity(a, b)
        assert sim >= 0.95

    def test_numbers_boost_crosslang_similarity(self):
        """Общие цифры сильно повышают кросс-язычную схожесть."""
        a = "Fed raises rates by 0.25%"
        b = "ФРС повысила ставку на 0.25%"
        sim = _title_similarity(a, b)
        assert sim >= 0.85

    def test_same_numbers_different_context(self):
        """Одинаковые цифры в разном контексте — средняя схожесть."""
        a = "Bitcoin hits 50000"
        b = "Биткоин достиг 50000"
        sim = _title_similarity(a, b)
        assert sim >= 0.75

    def test_russian_english_without_numbers_low(self):
        """Без цифр кросс-язычная схожесть низкая (ожидаемо)."""
        a = "Трамп встретился с Путиным"
        b = "Trump meets Putin"
        sim = _title_similarity(a, b)
        # Без общих цифр и с разными алфавитами — низкая схожесть
        assert sim < 0.5

    def test_different_topics_low_similarity(self):
        """Разные темы — низкая схожесть."""
        a = "Bitcoin reaches new all-time high"
        b = "Oil prices fall amid recession fears"
        sim = _title_similarity(a, b)
        assert sim < 0.7

    def test_deduplicate_removes_exact_duplicates(self):
        """Дедупликация удаляет точные дубли."""
        articles = [
            {"title": "Trump signs new sanctions bill", "score": 9, "link": "https://a.com"},
            {"title": "Trump signs new sanctions bill", "score": 8, "link": "https://b.com"},
            {"title": "Bitcoin price surges", "score": 7, "link": "https://c.com"},
        ]
        result = deduplicate_articles(articles, similarity_threshold=0.72)
        # Должно остаться 2: первая (score 9) + третья
        assert len(result) == 2
        assert result[0]["link"] == "https://a.com"
        assert result[1]["link"] == "https://c.com"

    def test_deduplicate_keeps_higher_score(self):
        """При дублях оставляем статью с более высоким score."""
        articles = [
            {"title": "Trump meets Putin today", "score": 8, "link": "https://b.com"},
            {"title": "Trump meets Putin today", "score": 9, "link": "https://a.com"},
        ]
        result = deduplicate_articles(articles, similarity_threshold=0.72)
        assert len(result) == 1
        # Оставляем более высокий score
        assert result[0]["link"] == "https://a.com"

    def test_deduplicate_with_numbers_crosslang(self):
        """Дедупликация с общими цифрами на разных языках."""
        articles = [
            {"title": "Fed raises rates by 0.25%", "score": 9, "link": "https://a.com"},
            {"title": "ФРС повысила ставку на 0.25%", "score": 8, "link": "https://b.com"},
            {"title": "Oil prices stable", "score": 5, "link": "https://c.com"},
        ]
        result = deduplicate_articles(articles, similarity_threshold=0.72)
        # С цифрами должны быть похожи
        assert len(result) == 2

    def test_no_false_positives_unrelated(self):
        """Не связанные новости не считаются дублями."""
        a = "Apple releases new iPhone"
        b = "Apple farmers expect good harvest"
        sim = _title_similarity(a, b)
        # "Apple" общее, но контекст разный
        assert sim < 0.85

    def test_deduplicate_empty_list(self):
        """Пустой список — пустой результат."""
        assert deduplicate_articles([]) == []

    def test_deduplicate_single_article(self):
        """Одна статья — остаётся одна."""
        articles = [
            {"title": "Test", "score": 5, "link": "https://example.com"},
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 1
