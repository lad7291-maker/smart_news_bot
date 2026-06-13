"""
Tests for P2-006: AI-cost tracking and alerts.
"""

import pytest

from storage.analytics import AnalyticsManager


class TestAICostTracking:
    @pytest.fixture
    def manager(self):
        return AnalyticsManager(db_path=":memory:")

    def test_record_ai_usage(self, manager):
        manager.record_ai_usage(
            provider="routerai",
            model="deepseek/deepseek-chat",
            tokens_input=1000,
            tokens_output=500,
            cost_usd=0.00035,
            article_title="Test",
        )
        daily = manager.get_ai_cost(days=1)
        assert daily["requests"] == 1
        assert daily["tokens_input"] == 1000
        assert daily["tokens_output"] == 500
        assert daily["cost_usd"] == 0.00035

    def test_ai_cost_aggregation(self, manager):
        manager.record_ai_usage("routerai", "deepseek", 1000, 500, 0.00035)
        manager.record_ai_usage("routerai", "deepseek", 2000, 800, 0.00056)
        manager.record_ai_usage("yandex", "yandexgpt", 500, 200, 0.0)

        daily = manager.get_ai_cost(days=1)
        assert daily["requests"] == 3
        assert daily["tokens_input"] == 3500
        assert daily["tokens_output"] == 1500
        assert abs(daily["cost_usd"] - 0.00091) < 0.00001

    def test_ai_cost_by_provider(self, manager):
        manager.record_ai_usage("routerai", "deepseek", 1000, 500, 0.00035)
        manager.record_ai_usage("yandex", "yandexgpt", 500, 200, 0.0)

        by_provider = manager.get_ai_cost_by_provider(days=7)
        assert len(by_provider) == 2

        routerai = next(p for p in by_provider if p["provider"] == "routerai")
        assert routerai["requests"] == 1
        assert routerai["total_cost"] == 0.00035

    def test_ai_cost_alert_below_threshold(self, manager):
        manager.record_ai_usage("routerai", "deepseek", 1000, 500, 0.5)
        alert, spent = manager.check_ai_cost_alert(daily_budget=10.0)
        assert alert is False
        assert spent == 0.5

    def test_ai_cost_alert_above_threshold(self, manager):
        manager.record_ai_usage("routerai", "deepseek", 1000, 500, 15.0)
        alert, spent = manager.check_ai_cost_alert(daily_budget=10.0)
        assert alert is True
        assert spent == 15.0

    def test_ai_cost_no_data(self, manager):
        daily = manager.get_ai_cost(days=1)
        assert daily["requests"] == 0
        assert daily["cost_usd"] == 0.0

    def test_ai_cost_by_provider_empty(self, manager):
        by_provider = manager.get_ai_cost_by_provider(days=7)
        assert by_provider == []

    def test_ai_cost_old_data_excluded(self, manager):
        """Старые записи (> 1 дня) не попадают в daily отчёт."""
        from datetime import datetime, timedelta

        # Эмулируем старую запись через прямой SQL
        cursor = manager.conn.cursor()
        old_time = (datetime.now() - timedelta(days=2)).isoformat()
        cursor.execute(
            """
            INSERT INTO ai_usage (provider, model, tokens_input, tokens_output, cost_usd, used_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            ("routerai", "deepseek", 1000, 500, 5.0, old_time),
        )
        manager.conn.commit()

        daily = manager.get_ai_cost(days=1)
        assert daily["requests"] == 0
        assert daily["cost_usd"] == 0.0

        # Но попадает в weekly
        weekly = manager.get_ai_cost(days=7)
        assert weekly["requests"] == 1
        assert weekly["cost_usd"] == 5.0
