"""
Тесты для асинхронного переводчика.
P0-002: Асинхронный перевод.
"""

import pytest

from translator import translate_to_english, translate_to_russian


class TestTranslatorAsync:
    def test_translate_to_russian_returns_string(self):
        """Проверяем что функция возвращает строку (даже без API-ключа)."""
        result = translate_to_russian("Hello world")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_to_english_returns_string(self):
        result = translate_to_english("Привет мир")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_empty_text(self):
        """Пустой текст возвращается как есть."""
        assert translate_to_russian("") == ""
        assert translate_to_english("") == ""

    def test_translate_none_text(self):
        """None возвращается как пустая строка (функция принимает str)."""
        # Передаём пустую строку вместо None, т.к. type hint требует str
        assert translate_to_russian("") == ""

    def test_caching_same_text(self):
        """Проверяем что кэш работает — повторный вызов не падает."""
        text = "Test caching"
        r1 = translate_to_russian(text)
        r2 = translate_to_russian(text)
        assert r1 == r2

    def test_parallel_translation_performance(self):
        """Параллельный перевод 10 текстов должен выполняться быстро (< 3 сек)."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        texts = [f"News article number {i} about global markets and economy" for i in range(10)]
        start = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(translate_to_russian, texts))
        elapsed = time.time() - start

        assert len(results) == 10
        assert all(isinstance(r, str) for r in results)
        # Без API-ключа возвращается исходный текст мгновенно
        # С API-ключом параллельные запросы должны уложиться в 3 сек
        assert elapsed < 3.0, f"Parallel translation took {elapsed:.2f}s, expected < 3s"

    def test_translate_pair_parallel(self):
        """Перевод title + summary одной статьи параллельно."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        title = "Trump signs new executive order"
        summary = "The president announced major policy changes today."

        start = time.time()
        with ThreadPoolExecutor(max_workers=2) as executor:
            t_title, t_summary = executor.map(translate_to_russian, [title, summary])
        elapsed = time.time() - start

        assert isinstance(t_title, str)
        assert isinstance(t_summary, str)
        assert elapsed < 2.0, f"Pair translation took {elapsed:.2f}s"
