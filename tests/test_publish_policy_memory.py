"""
Тесты для P2-006: Оптимизация памяти _recent_publishes.

Покрывают:
- deque maxlen ограничивает рост
- record_publish работает корректно
- get_recent_stats не падает с deque
"""

import pytest

from utils.publish_policy import (
    _cleanup_old_records,
    _recent_publishes,
    get_recent_stats,
    record_publish,
)


class TestDequeMaxlen:
    """Тесты ограничения размера deque."""

    def test_deque_has_maxlen(self):
        assert _recent_publishes.maxlen == 1000

    def test_deque_does_not_grow_beyond_maxlen(self):
        # Очищаем
        _recent_publishes.clear()
        # Добавляем 1100 записей
        for i in range(1100):
            record_publish(score=5, title=f"News {i}", source="Test")
        assert len(_recent_publishes) <= 1000
        # Проверяем, что старые записи вытеснены
        titles = [r["title"] for r in _recent_publishes]
        assert "News 0" not in titles
        assert "News 1099" in titles

    def test_record_publish_adds_entry(self):
        _recent_publishes.clear()
        record_publish(score=8, title="Test Article", source="TestSource")
        assert len(_recent_publishes) == 1
        entry = _recent_publishes[0]
        assert entry["score"] == 8
        assert entry["title"] == "Test Article"
        assert entry["source"] == "TestSource"
        assert entry["level"] == "orange"

    def test_get_recent_stats_works_with_deque(self):
        _recent_publishes.clear()
        record_publish(score=10, title="Red News", source="Test")
        record_publish(score=5, title="Yellow News", source="Test")
        stats = get_recent_stats(hours=1.0)
        assert stats["total"] == 2
        assert stats["red"] == 1
        assert stats["yellow"] == 1
        assert stats["orange"] == 0

    def test_cleanup_old_records_works_with_deque(self):
        _recent_publishes.clear()
        record_publish(score=5, title="Old", source="Test")
        # cleanup не должен падать
        _cleanup_old_records()
        assert len(_recent_publishes) >= 0  # может очистить, может оставить
