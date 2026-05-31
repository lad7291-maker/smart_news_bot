"""
Фикстуры для тестов Smart News Bot.
"""
import asyncio
import pytest
import sqlite3
import tempfile
import os
from pathlib import Path


@pytest.fixture(scope="session")
def event_loop():
    """Создаёт единый event loop для всех async тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def tmp_db_path(tmp_path):
    """Временный путь для SQLite-базы."""
    return str(tmp_path / "test_cache.db")


@pytest.fixture
def mock_article():
    """Типовая новость для тестов."""
    from datetime import datetime
    return {
        "title": "Bitcoin вырос после решения SEC",
        "link": "https://example.com/news/1",
        "summary": "SEC одобрила ETF, цена биткоина превысила $70k.",
        "source": "CoinDesk",
        "source_tag": "CoinDesk",
        "published": datetime.now(),
        "type": "rss",
    }


@pytest.fixture
def mock_articles_list():
    """Список новостей для тестов дедупликации."""
    from datetime import datetime
    base = datetime.now()
    return [
        {
            "title": "Trump signs new tariff order",
            "link": "https://example.com/1",
            "summary": "The US president imposes 25% tariffs on steel.",
            "source": "CNBC_World",
            "published": base,
            "score": 9,
        },
        {
            "title": "Трамп подписал новый тарифный указ",
            "link": "https://example.ru/2",
            "summary": "Президент США ввёл пошлины 25% на сталь.",
            "source": "RIA",
            "published": base,
            "score": 9,
        },
        {
            "title": "Nvidia reports record earnings",
            "link": "https://example.com/3",
            "summary": "Q1 revenue exceeded expectations.",
            "source": "NYT_Tech",
            "published": base,
            "score": 5,
        },
    ]
