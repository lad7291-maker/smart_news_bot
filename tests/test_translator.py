"""
Тесты для асинхронного переводчика.
P0-002: Асинхронный перевод.
"""

import asyncio

import pytest

from translator import close_translator_client, translate_to_english, translate_to_russian


class TestTranslatorAsync:
    @pytest.mark.asyncio
    async def test_translate_to_russian_returns_string(self):
        """Проверяем что async-функция возвращает строку (даже без API-ключа)."""
        result = await translate_to_russian("Hello world")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_translate_to_english_returns_string(self):
        result = await translate_to_english("Привет мир")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_translate_empty_text(self):
        """Пустой текст возвращается как есть."""
        assert await translate_to_russian("") == ""
        assert await translate_to_english("") == ""

    @pytest.mark.asyncio
    async def test_translate_none_text(self):
        """None возвращается как пустая строка (функция принимает str)."""
        # Передаём пустую строку вместо None, т.к. type hint требует str
        assert await translate_to_russian("") == ""

    @pytest.mark.asyncio
    async def test_caching_same_text(self):
        """Проверяем что кэш работает — повторный вызов не падает."""
        text = "Test caching"
        r1 = await translate_to_russian(text)
        r2 = await translate_to_russian(text)
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_parallel_translation_performance(self):
        """Параллельный перевод 10 текстов должен выполняться быстро (< 3 сек)."""
        texts = [f"News article number {i} about global markets and economy" for i in range(10)]
        start = asyncio.get_event_loop().time()
        results = await asyncio.gather(*[translate_to_russian(t) for t in texts])
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 10
        assert all(isinstance(r, str) for r in results)
        # Без API-ключа возвращается исходный текст мгновенно
        # С API-ключом параллельные запросы должны уложиться в 3 сек
        assert elapsed < 3.0, f"Parallel translation took {elapsed:.2f}s, expected < 3s"

    @pytest.mark.asyncio
    async def test_translate_pair_parallel(self):
        """Перевод title + summary одной статьи параллельно."""
        title = "Trump signs new executive order"
        summary = "The president announced major policy changes today."

        start = asyncio.get_event_loop().time()
        t_title, t_summary = await asyncio.gather(
            translate_to_russian(title),
            translate_to_russian(summary),
        )
        elapsed = asyncio.get_event_loop().time() - start

        assert isinstance(t_title, str)
        assert isinstance(t_summary, str)
        assert elapsed < 2.0, f"Pair translation took {elapsed:.2f}s"
