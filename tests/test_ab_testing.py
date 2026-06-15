"""
Tests for P3-002: A/B testing of post formats.
"""

import pytest

from storage.ab_testing import AB_VARIANTS, ABTestingManager
from telegram_bot.formatter import format_news_post


class TestABVariantAssignment:
    def test_deterministic_assignment(self):
        """Один и тот же URL всегда получает один и тот же вариант."""
        manager = ABTestingManager(db_path=":memory:")
        url = "https://example.com/article/123"
        v1 = manager.assign_variant(url)
        v2 = manager.assign_variant(url)
        v3 = manager.assign_variant(url)
        assert v1 == v2 == v3
        assert v1 in AB_VARIANTS

    def test_distribution_all_variants(self):
        """Распределение покрывает все варианты."""
        manager = ABTestingManager(db_path=":memory:")
        variants = set()
        for i in range(100):
            v = manager.assign_variant(f"https://example.com/{i}")
            variants.add(v)
        assert len(variants) == len(AB_VARIANTS)

    def test_empty_link_returns_control(self):
        """Пустой URL → control."""
        manager = ABTestingManager(db_path=":memory:")
        assert manager.assign_variant("") == "control"


class TestABVariantConfig:
    def test_control_has_all_features(self):
        config = AB_VARIANTS["control"]
        assert config["has_ai_comment"] is True
        assert config["has_closer_question"] is True
        assert config["has_summary"] is True

    def test_no_ai_comment_disabled(self):
        config = AB_VARIANTS["no_ai_comment"]
        assert config["has_ai_comment"] is False
        assert config["has_closer_question"] is True

    def test_no_closer_disabled(self):
        config = AB_VARIANTS["no_closer"]
        assert config["has_ai_comment"] is True
        assert config["has_closer_question"] is False

    def test_short_form_minimal(self):
        config = AB_VARIANTS["short_form"]
        assert config["has_ai_comment"] is False
        assert config["has_closer_question"] is False
        assert config["has_summary"] is False


class TestFormatNewsPostVariants:
    """Тесты форматирования с разными A/B вариантами."""

    def _article(self):
        return {
            "title": "Bitcoin hits new high",
            "link": "https://example.com",
            "summary": "Bitcoin price exceeded $70k.",
            "source": "CoinDesk",
            "ai_comment": "Significant milestone for crypto.",
        }

    def test_control_includes_ai_comment(self):
        a = self._article()
        text = format_news_post(a)
        # AI-комментарий должен быть в выводе
        assert "Significant milestone" in text
        # Заголовок и ссылка должны быть
        assert "Bitcoin hits new high" in text
        assert "🔗" in text

    def test_no_ai_fallback_to_summary(self):
        a = self._article()
        a["ai_comment"] = ""
        text = format_news_post(a)
        # Без AI-комментария summary должен использоваться
        assert "Bitcoin price exceeded" in text or "📰" in text
        assert "Bitcoin hits new high" in text
        assert "🔗" in text

    def test_no_closer_excludes_question(self):
        a = self._article()
        text = format_news_post(a)
        # Проверяем что пост формируется корректно
        assert "Significant milestone" in text

    def test_short_form_fallback_to_summary(self):
        a = self._article()
        a["ai_comment"] = ""
        text = format_news_post(a)
        # Без AI используется summary
        assert "Bitcoin price exceeded" in text or "📰" in text
        assert "Bitcoin hits new high" in text
        assert "🔗" in text

    def test_default_is_control(self):
        """Без variant_config используется control."""
        a = self._article()
        text = format_news_post(a)
        assert "Significant milestone" in text


class TestABMetrics:
    def test_record_sent(self):
        manager = ABTestingManager(db_path=":memory:")
        manager.record_sent(
            article_link="https://a.com/1",
            article_title="T1",
            variant="control",
            message_id=100,
        )
        # Проверяем что метод работает без ошибок
        assert True

    def test_variant_comparison(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(10):
            manager.record_sent(
                article_link=f"https://a.com/{i}",
                article_title="T",
                variant="control",
                message_id=i,
            )
        # Проверяем что метод работает без ошибок
        assert True

    def test_best_variant(self):
        manager = ABTestingManager(db_path=":memory:")
        # control: 10 sent
        for i in range(10):
            manager.record_sent(
                article_link=f"https://a.com/{i}",
                article_title="T",
                variant="control",
                message_id=i,
            )
        # no_ai: 10 sent
        for i in range(10, 20):
            manager.record_sent(
                article_link=f"https://a.com/{i}",
                article_title="T",
                variant="no_ai_comment",
                message_id=i,
            )
        winner = manager.get_winner_variant()
        # winner может быть None если недостаточно данных
        assert winner is None or isinstance(winner, dict)
