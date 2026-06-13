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
        text = format_news_post(a, AB_VARIANTS["control"])
        # AI-комментарий должен быть в выводе с префиксом 📌
        assert "📌 Significant milestone" in text
        # Оригинальный summary НЕ должен дублироваться
        assert "Bitcoin price exceeded" not in text

    def test_no_ai_fallback_to_summary(self):
        a = self._article()
        text = format_news_post(a, AB_VARIANTS["no_ai_comment"])
        # AI-комментарий отключен — fallback на оригинальный summary
        assert "Significant milestone" not in text
        assert "📌 Bitcoin price exceeded" in text
        # Заголовок и ссылка должны быть
        assert "Bitcoin hits new high" in text
        assert "🔗" in text

    def test_no_closer_excludes_question(self):
        a = self._article()
        text = format_news_post(a, AB_VARIANTS["no_closer"])
        assert "Что думаете?" not in text
        assert "📌 Significant milestone" in text

    def test_short_form_fallback_to_summary(self):
        a = self._article()
        text = format_news_post(a, AB_VARIANTS["short_form"])
        # short_form отключает AI — fallback на summary
        assert "Significant milestone" not in text
        assert "📌 Bitcoin price exceeded" in text
        assert "Bitcoin hits new high" in text
        assert "🔗" in text

    def test_default_is_control(self):
        """Без variant_config используется control."""
        a = self._article()
        text = format_news_post(a)
        assert "📌 Significant milestone" in text


class TestABMetrics:
    def test_record_sent_and_results(self):
        manager = ABTestingManager(db_path=":memory:")
        manager.record_sent(
            article_link="https://a.com/1",
            article_title="T1",
            variant="control",
            message_id=100,
            has_image=True,
            score=8,
        )
        results = manager.get_results(days=1)
        control = next(r for r in results if r["variant"] == "control")
        assert control["impressions"] == 1

    def test_record_reaction(self):
        manager = ABTestingManager(db_path=":memory:")
        manager.record_reaction("control", "like")
        manager.record_reaction("control", "like")
        manager.record_reaction("control", "save")
        results = manager.get_results(days=1)
        control = next(r for r in results if r["variant"] == "control")
        assert control["reactions"] == 2
        assert control["saves"] == 1

    def test_ctr_calculation(self):
        manager = ABTestingManager(db_path=":memory:")
        manager.record_sent("https://a.com/1", "T1", "control", message_id=1)
        manager.record_sent("https://a.com/2", "T2", "control", message_id=2)
        manager.record_reaction("control", "like")
        results = manager.get_results(days=1)
        control = next(r for r in results if r["variant"] == "control")
        assert control["impressions"] == 2
        assert control["reactions"] == 1
        assert control["ctr"] == 50.0

    def test_report_text_no_data(self):
        manager = ABTestingManager(db_path=":memory:")
        text = manager.get_report_text(days=7)
        assert "Нет данных" in text

    def test_report_text_with_data(self):
        manager = ABTestingManager(db_path=":memory:")
        manager.record_sent("https://a.com/1", "T1", "control", message_id=1)
        manager.record_reaction("control", "like")
        text = manager.get_report_text(days=7)
        assert "Контроль" in text
        assert "CTR" in text
