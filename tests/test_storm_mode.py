"""
Tests for Storm Mode behavior (P1-005).
Проверяет rate limiting и режим шторма при burst'е red-новостей.
"""

from datetime import datetime, timedelta

import pytest

from utils import publish_policy


class TestStormMode:
    """Тесты режима шторма и rate limiting."""

    def setup_method(self):
        """Очищаем историю публикаций перед каждым тестом."""
        publish_policy._recent_publishes.clear()

    def test_quiet_mode_initial(self):
        """Без публикаций (0 red, 0 orange) — режим QUIET."""
        assert publish_policy.get_mode() == "quiet"

    def test_storm_mode_after_3_red(self):
        """3 red-новости за час — режим STORM."""
        for i in range(3):
            publish_policy.record_publish(score=9, title=f"Red {i}", source="Test")
        assert publish_policy.get_mode() == "storm"

    def test_not_storm_with_2_red(self):
        """2 red-новости — ещё не шторм."""
        for i in range(2):
            publish_policy.record_publish(score=9, title=f"Red {i}", source="Test")
        assert publish_policy.get_mode() == "normal"

    def test_quiet_mode_no_red(self):
        """0 red и 1 orange — режим QUIET."""
        publish_policy.record_publish(score=7, title="Orange", source="Test")
        assert publish_policy.get_mode() == "quiet"

    def test_rate_limit_max_8_per_hour(self):
        """Не более 8 постов в час."""
        # 8 публикаций
        for i in range(8):
            publish_policy.record_publish(score=5, title=f"Post {i}", source="Test")

        stats = publish_policy.get_recent_stats(hours=1.0)
        assert stats["total"] == 8

        # 9-я должна быть заблокирована rate limit
        allowed, reason = publish_policy.should_publish(
            level="orange", score=7, mode="normal", quiet=False
        )
        assert allowed is False
        assert "rate_limit" in reason

    def test_red_always_allowed_even_in_storm(self):
        """Red-новости всегда публикуются, даже в шторм."""
        for i in range(5):
            publish_policy.record_publish(score=9, title=f"Red {i}", source="Test")

        assert publish_policy.get_mode() == "storm"

        # Red 10 — всегда allowed
        allowed, reason = publish_policy.should_publish(
            level="red", score=10, mode="storm", quiet=False
        )
        assert allowed is True

    def test_red_deferred_at_night(self):
        """Red 9 откладывается в тихие часы."""
        # Мокаем тихие часы
        night_time = datetime(2026, 6, 4, 2, 0, 0)  # 02:00 ночи
        assert publish_policy.is_quiet_hours(night_time) is True

        allowed, reason = publish_policy.should_publish(
            level="red", score=9, mode="normal", quiet=True
        )
        assert allowed is False
        assert "deferred" in reason

    def test_red_10_always_immediate(self):
        """Red 10 публикуется даже ночью."""
        allowed, reason = publish_policy.should_publish(
            level="red", score=10, mode="normal", quiet=True
        )
        assert allowed is True

    def test_orange_blocked_in_quiet_hours(self):
        """Orange блокируется в тихие часы."""
        allowed, reason = publish_policy.should_publish(
            level="orange", score=7, mode="normal", quiet=True
        )
        assert allowed is False
        assert "quiet_hours" in reason

    def test_yellow_delayed_in_normal(self):
        """Yellow откладывается в обычном режиме."""
        allowed, reason = publish_policy.should_publish(
            level="yellow", score=5, mode="normal", quiet=False
        )
        assert allowed is True
        assert "delayed" in reason

    def test_cleanup_old_records(self):
        """Старые записи (>2ч) удаляются."""
        # Добавляем старую запись
        old_record = {
            "score": 9,
            "level": "red",
            "title": "Old",
            "source": "Test",
            "ts": datetime.now() - timedelta(hours=3),
        }
        publish_policy._recent_publishes.append(old_record)

        # Добавляем свежую
        publish_policy.record_publish(score=9, title="New", source="Test")

        # Старая должна быть удалена
        stats = publish_policy.get_recent_stats(hours=2.0)
        assert stats["total"] == 1

    def test_storm_mode_orange_delayed(self):
        """В шторм orange публикуется с задержкой."""
        for i in range(3):
            publish_policy.record_publish(score=9, title=f"Red {i}", source="Test")

        allowed, reason = publish_policy.should_publish(
            level="orange", score=7, mode="storm", quiet=False
        )
        assert allowed is True
        assert "storm" in reason

    def test_delay_red_is_zero(self):
        """Задержка для red = 0."""
        delay = publish_policy.get_delay_seconds("red", 9, "normal", False)
        assert delay == 0

    def test_delay_yellow_in_normal(self):
        """Задержка для yellow в обычном режиме = 2-4 часа."""
        delay = publish_policy.get_delay_seconds("yellow", 5, "normal", False)
        assert delay >= 7200  # минимум 2 часа
