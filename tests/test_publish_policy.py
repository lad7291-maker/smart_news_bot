"""
Тесты для политики публикаций.
FEAT-001: Проверка, что yellow-новости не теряются массово.
FEAT-012: Покрытие логики should_publish / get_delay_seconds.
"""
import pytest
from datetime import datetime
from utils import publish_policy


class TestPublishPolicy:
    def test_get_publish_level_red(self):
        assert publish_policy.get_publish_level(10) == "red"
        assert publish_policy.get_publish_level(9) == "red"

    def test_get_publish_level_orange(self):
        assert publish_policy.get_publish_level(8) == "orange"
        assert publish_policy.get_publish_level(7) == "orange"

    def test_get_publish_level_yellow(self):
        assert publish_policy.get_publish_level(6) == "yellow"
        assert publish_policy.get_publish_level(1) == "yellow"

    def test_red_always_allowed(self):
        allowed, reason = publish_policy.should_publish("red", 10, "normal", quiet=False)
        assert allowed is True

    def test_red_deferred_at_night(self):
        allowed, reason = publish_policy.should_publish("red", 9, "normal", quiet=True)
        assert allowed is False
        assert "deferred" in reason

    def test_orange_blocked_in_quiet_hours(self):
        allowed, reason = publish_policy.should_publish("orange", 7, "normal", quiet=True)
        assert allowed is False
        assert "quiet" in reason

    def test_topic_cooldown_ignores_red(self):
        ok, reason, sec = publish_policy.check_topic_cooldown("Trump meets Putin", "red")
        assert ok is True
        assert sec == 0

    def test_topic_cooldown_blocks_orange(self):
        # Симулируем недавнюю публикацию по теме
        publish_policy._recent_publishes.clear()
        publish_policy.record_publish(7, "Trump announces new policy", "CNBC")
        ok, reason, sec = publish_policy.check_topic_cooldown("Trump signs order", "orange")
        assert ok is False
        assert "cooldown" in reason
        assert sec > 0

    def test_delay_red_is_zero(self):
        delay = publish_policy.get_delay_seconds("red", 10, "normal", quiet=False)
        assert delay == 0

    def test_delay_yellow_in_normal_mode(self):
        delay = publish_policy.get_delay_seconds("yellow", 5, "normal", quiet=False)
        assert delay is not None
        assert 7200 <= delay <= 14400

    def test_simulated_collection_retains_majority(self):
        """
        FEAT-001: Симуляция сбора новостей.
        Из смеси red/orange/yellow должно быть опубликовано >50%.
        """
        from utils.publish_policy import should_publish, get_publish_level
        articles = [
            {"score": 10, "title": "A"},
            {"score": 9, "title": "B"},
            {"score": 8, "title": "C"},
            {"score": 7, "title": "D"},
            {"score": 6, "title": "E"},
            {"score": 5, "title": "F"},
            {"score": 4, "title": "G"},
            {"score": 3, "title": "H"},
            {"score": 2, "title": "I"},
            {"score": 1, "title": "J"},
        ]
        mode = "normal"
        quiet = False
        allowed_count = 0
        for a in articles:
            level = get_publish_level(a["score"])
            allowed, _ = should_publish(level, a["score"], mode, quiet)
            if allowed:
                allowed_count += 1
        # В текущей логике yellow всегда allowed=True (с задержкой)
        # red и orange тоже allowed в normal mode
        assert allowed_count >= len(articles) // 2, (
            f"FEAT-001: Only {allowed_count}/{len(articles)} articles allowed. "
            f"Too many yellow news are lost."
        )
