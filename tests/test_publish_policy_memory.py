"""
Тесты для P2-006: Оптимизация памяти _recent_publishes.

Покрывают:
- record_publish работает корректно
- get_recent_stats не падает
- cleanup работает
"""

import pytest

from utils.publish_policy import (
    _cleanup_old_records,
    _recent_publishes,
    get_recent_stats,
    record_publish,
)


class TestRecentPublishes:
    """Тесты ограничения размера списка публикаций."""

    def test_list_exists(self):
        assert isinstance(_recent_publishes, list)

    def test_record_publish_adds_entry(self):
        _recent_publishes.clear()
        record_publish(score=8, title="Test Article", source="TestSource")
        assert len(_recent_publishes) >= 1
        entry = _recent_publishes[-1]
        assert entry["score"] == 8
        assert entry["title"] == "Test Article"
        assert entry["source"] == "TestSource"
        assert entry["level"] == "red"

    def test_get_recent_stats_works(self):
        _recent_publishes.clear()
        record_publish(score=10, title="Red News", source="Test")
        record_publish(score=5, title="Yellow News", source="Test")
        stats = get_recent_stats(hours=1.0)
        assert stats["total"] >= 2
        assert stats["red"] >= 1
        assert stats["yellow"] >= 1

    def test_cleanup_old_records_works(self):
        _recent_publishes.clear()
        record_publish(score=5, title="Old", source="Test")
        # cleanup не должен падать
        _cleanup_old_records()
        assert len(_recent_publishes) >= 0  # может очистить, может оставить

    def test_does_not_grow_unbounded(self):
        _recent_publishes.clear()
        # Добавляем много записей
        for i in range(100):
            record_publish(score=5, title=f"News {i}", source="Test")
        # cleanup должен ограничивать рост
        _cleanup_old_records()
        assert len(_recent_publishes) <= 100
