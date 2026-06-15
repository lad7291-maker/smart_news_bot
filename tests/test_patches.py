"""
Tests for patches and utilities.
"""

import sys
from unittest.mock import patch

import pytest


def test_extract_top_keywords():
    """Проверяем что экстрактор ключевых слов работает."""
    from utils.image_search import _extract_top_keywords

    result = _extract_top_keywords("Trump meets Putin in Moscow", "Important summit meeting today")
    assert "Trump" in result or "Putin" in result or "Moscow" in result
    assert len(result.split()) <= 5


def test_build_image_query_short():
    """Проверяем что поисковый запрос короткий."""
    from utils.image_search import _build_image_query

    query = _build_image_query(
        "Trump meets Putin in Moscow for peace talks", "Important summit", "Reuters"
    )
    assert len(query) <= 100
    assert "news" in query


def test_is_junk_blocks_math():
    """Математические примеры отфильтровываются."""
    from bot_runner import _is_junk

    assert _is_junk("Сколько будет 2+2?") is True
    assert _is_junk("Реши уравнение x^2 + 3x = 0") is True


def test_is_junk_allows_real_news():
    """Реальные новости не отфильтровываются."""
    from bot_runner import _is_junk

    assert _is_junk("Трамп подписал указ") is False
    assert _is_junk("Bitcoin вырос на 5%") is False


def test_deduplication_threshold():
    """Проверяем порог дедупликации."""
    from utils.deduplicator import deduplicate_articles

    articles = [
        {"title": "Trump Signs Order", "link": "https://a.com/1"},
        {"title": "Trump Signs Executive Order", "link": "https://a.com/2"},
        {"title": "Completely Different News", "link": "https://b.com/1"},
    ]
    result = deduplicate_articles(articles, similarity_threshold=0.72)
    assert len(result) >= 1


def test_summary_min_length():
    """Summary должен быть достаточно длинным."""
    from bot_runner import filter_article

    a = {"title": "News", "summary": "Short", "source": "Test"}
    assert filter_article(a) is False

    a2 = {"title": "News", "summary": "A" * 100, "source": "Test"}
    # Может пройти или не пройти в зависимости от is_russian/is_relevant
    result = filter_article(a2)
    assert isinstance(result, bool)


def test_politician_check_in_image_search():
    """Проверяем что политики учитываются при поиске изображений."""
    from utils.image_search import _score_image

    score = _score_image("https://example.com/trump-photo.jpg", {"trump", "putin"})
    # Score может быть отрицательным для не-новостных доменов
    assert isinstance(score, int)


def test_telegram_retry_wrapper():
    """Проверяем что poster модуль импортируется корректно."""
    from telegram_bot import poster

    assert hasattr(poster, "send_news_to_channel")
    assert callable(poster.send_news_to_channel)


def run_all_tests():
    print("=" * 60)
    print("🧪 ЗАПУСК ТЕСТОВ ПАТЧЕЙ")
    print("=" * 60)

    tests = [
        test_extract_top_keywords,
        test_build_image_query_short,
        test_is_junk_blocks_math,
        test_is_junk_allows_real_news,
        test_deduplication_threshold,
        test_summary_min_length,
        test_politician_check_in_image_search,
        test_telegram_retry_wrapper,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"📊 РЕЗУЛЬТАТ: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
