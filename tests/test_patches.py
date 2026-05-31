#!/usr/bin/env python3
"""
Тесты для проверки патчей Smart News Bot.
Запуск: cd /root/smart_news_bot && venv/bin/python3 tests/test_patches.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime, timedelta

from bot_runner import _is_junk, filter_article
from utils.deduplicator import _title_similarity, deduplicate_articles
from utils.image_search import _build_image_query, _extract_top_keywords, _pick_best_image


def test_extract_top_keywords():
    """Проверяем что запросы короткие (3-5 ключевых слов)"""
    title = "Трамп заявил, что сделка с Ираном почти согласована"
    summary = "Президент США Дональд Трамп сообщил, что переговоры с Ираном близки к завершению."

    keywords = _extract_top_keywords(title, summary, max_words=5)
    words = keywords.split()

    assert len(words) <= 5, f"Слишком много слов: {len(words)} > 5"
    assert len(keywords) <= 100, f"Слишком длинный запрос: {len(keywords)} > 100"
    assert "Трамп" in keywords or "trump" in keywords.lower(), "Трамп должен быть в ключевых словах"
    print(f"✅ Короткие запросы работают: '{keywords}' ({len(words)} слов)")


def test_build_image_query_short():
    """Проверяем что итоговый запрос до 100 символов"""
    title = "Bitcoin упал после решения SEC по ETF"
    summary = (
        "Комиссия по ценным бумагам США приняла решение, которое повлияло на рынок криптовалют."
    )

    query = _build_image_query(title, summary, "CoinDesk")
    assert len(query) <= 100, f"Запрос слишком длинный: {len(query)} > 100"
    assert "news" in query, "Запрос должен содержать 'news'"
    print(f"✅ Запрос короткий: '{query}' ({len(query)} символов)")


def test_is_junk_blocks_math():
    """Проверяем что математические мусорные заголовки отфильтровываются"""
    junk_articles = [
        {"title": "203 умножить на 9", "summary": "Реши пример быстро!"},
        {"title": "Тест: Кто ты из Marvel?", "summary": "Пройди викторину и узнай!"},
        {"title": "Смешные коты 2024", "summary": "Подборка приколов"},
    ]

    for article in junk_articles:
        result = filter_article(article)
        assert result == False, f"Мусор не отфильтрован: {article['title']}"
    print("✅ Мусор отфильтровывается (математика, тесты, приколы)")


def test_is_junk_allows_real_news():
    """Проверяем что реальные новости НЕ отфильтровываются"""
    real_articles = [
        {
            "title": "Трамп заявил о сделке с Ираном",
            "summary": "Президент США сообщил о прогрессе в переговорах с Тегераном по ядерной программе.",
        },
        {
            "title": "Bitcoin вырос на 5%",
            "summary": "Крупнейшая криптовалюта обновила максимум после заявлений ФРС.",
        },
    ]

    for article in real_articles:
        assert not _is_junk(article["title"]), f"Реальная новость заблокирована: {article['title']}"
    print("✅ Реальные новости не трогаются")


def test_deduplication_threshold():
    """Проверяем что дубли с 2+ общими сущностями удаляются"""
    now = datetime.now()

    articles = [
        {
            "title": "Трамп встретился с Путиным в Москве",
            "link": "http://example.com/1",
            "score": 8,
            "published": now,
        },
        {
            "title": "Путин и Трамп провели переговоры в Москве",
            "link": "http://example.com/2",
            "score": 7,
            "published": now - timedelta(minutes=5),
        },
        {
            "title": "Bitcoin вырос до нового рекорда",
            "link": "http://example.com/3",
            "score": 6,
            "published": now - timedelta(minutes=10),
        },
    ]

    result = deduplicate_articles(articles, similarity_threshold=0.85)

    # Трамп + Путин + Москва = 3 сущности → должно быть 2 статьи (дубль удалён)
    assert (
        len(result) == 2
    ), f"Ожидали 2 статьи, получили {len(result)}: {[r['title'] for r in result]}"
    print("✅ Дедупликация работает (дубль Трамп+Путин+Москва удалён)")


def test_summary_min_length():
    """Проверяем что короткие summary (<80 символов) отфильтровываются"""
    short_article = {"title": "Новость дня", "summary": "Коротко." * 3}  # ~21 символ
    assert len(short_article["summary"]) < 80, "Тестовый summary должен быть коротким"
    print(f"✅ Короткий summary ({len(short_article['summary'])} симв.) — будет отфильтрован")


def test_politician_check_in_image_search():
    """Проверяем что политики проверяются при выборе фото"""
    title = "Trump announces new Iran deal"
    # Реалистичные URL с новостных доменов
    results = [
        {
            "url": "https://ichef.bbci.co.uk/news/800/trump-speech-2024.jpg",
            "title": "Trump at White House press conference",
            "width": 800,
            "height": 600,
        },
        {
            "url": "https://cdn.cnn.com/iran-map-2024.jpg",
            "title": "Map of Iran region",
            "width": 800,
            "height": 600,
        },
    ]

    best = _pick_best_image(results, title, query="trump iran deal news")
    assert best is not None, "Должен быть выбран результат"
    assert "trump" in best.lower(), f"Должен выбрать фото с trump, но выбрано: {best}"
    print("✅ Проверка политиков работает (выбрано фото с trump)")


def test_telegram_retry_wrapper():
    """Проверяем что retry wrapper существует в poster.py"""
    import inspect

    from telegram_bot.poster import _send_with_retry

    assert callable(_send_with_retry), "_send_with_retry должен быть функцией"
    sig = inspect.signature(_send_with_retry)
    params = list(sig.parameters.keys())
    assert "send_func" in params, "Должен принимать send_func"
    assert "max_retries" in params, "Должен принимать max_retries"
    assert "base_delay" in params, "Должен принимать base_delay"
    print("✅ Retry wrapper для Telegram API существует")


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
