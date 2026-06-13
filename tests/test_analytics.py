"""
Тесты для модуля аналитики.
P0-001: Система аналитики и метрик доставки.
"""

from datetime import datetime, timedelta

import pytest

from storage.analytics import AnalyticsManager


class TestAnalyticsManager:
    def test_record_and_get_message_sent(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        ok = mgr.record_message_sent(
            message_id=12345,
            chat_id="@test_channel",
            article_link="https://example.com/news/1",
            article_title="Test News",
            source_tag="TestSource",
            score=8,
            delivered=True,
            has_image=True,
            is_fallback_image=False,
        )
        assert ok is True

        stats = mgr.get_delivery_stats(hours=1)
        assert stats["total_sent"] == 1
        assert stats["delivered"] == 1
        assert stats["delivery_rate"] == 100.0
        assert stats["with_image"] == 1
        assert stats["fallback_images"] == 0
        mgr.close()

    def test_record_failed_delivery(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        mgr.record_message_sent(
            message_id=None,
            chat_id="@test_channel",
            article_link="https://example.com/news/2",
            article_title="Failed News",
            source_tag="TestSource",
            score=5,
            delivered=False,
            has_image=False,
            is_fallback_image=False,
        )
        stats = mgr.get_delivery_stats(hours=1)
        assert stats["total_sent"] == 1
        assert stats["delivered"] == 0
        assert stats["delivery_rate"] == 0.0
        mgr.close()

    def test_record_delivery_error(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        mgr.record_delivery_error(
            error_type="FLOOD_WAIT",
            error_code=429,
            article_link="https://example.com/news/3",
            article_title="Flood Test",
            details="retry_after=30",
        )
        errors = mgr.get_error_stats(hours=1)
        assert errors["total_errors"] == 1
        assert errors["flood_wait"] == 1
        assert errors["api_errors"] == 0
        mgr.close()

    def test_record_network_error(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        mgr.record_delivery_error(
            error_type="NetworkError",
            article_link="https://example.com/news/4",
            details="Connection refused",
        )
        errors = mgr.get_error_stats(hours=1)
        assert errors["total_errors"] == 1
        assert errors["network_errors"] == 1
        mgr.close()

    def test_user_session_dau(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        mgr.record_user_session("user_1")
        mgr.record_user_session("user_2")
        mgr.record_user_session("user_1")  # тот же пользователь — увеличивает interactions

        dau = mgr.get_dau(days=1)
        assert dau == 2  # 2 уникальных пользователя
        mgr.close()

    def test_user_session_mau(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        # Записываем сессию за 5 дней назад
        mgr.record_user_session("old_user")
        # Подменяем дату на 5 дней назад
        mgr.conn.execute(
            "UPDATE user_sessions SET session_date = ? WHERE user_id = ?",
            ((datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"), "old_user"),
        )
        mgr.conn.commit()

        mau = mgr.get_mau()
        assert mau == 1
        mgr.close()

    def test_top_sources(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        for i in range(3):
            mgr.record_message_sent(
                message_id=i,
                chat_id="@ch",
                article_link=f"https://example.com/{i}",
                article_title=f"News {i}",
                source_tag="SourceA",
                score=7,
                delivered=True,
            )
        for i in range(2):
            mgr.record_message_sent(
                message_id=10 + i,
                chat_id="@ch",
                article_link=f"https://example.com/b{i}",
                article_title=f"News B {i}",
                source_tag="SourceB",
                score=5,
                delivered=True,
            )
        top = mgr.get_top_sources(days=1, limit=10)
        assert len(top) == 2
        assert top[0]["source_tag"] == "SourceA"
        assert top[0]["posts"] == 3
        assert top[1]["source_tag"] == "SourceB"
        assert top[1]["posts"] == 2
        mgr.close()

    def test_analytics_report_structure(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        mgr.record_message_sent(
            message_id=1,
            chat_id="@ch",
            article_link="https://example.com/1",
            article_title="Test",
            source_tag="Test",
            score=5,
            delivered=True,
        )
        report = mgr.get_analytics_report()
        assert "dau" in report
        assert "mau" in report
        assert "delivery_24h" in report
        assert "delivery_7d" in report
        assert "errors_24h" in report
        assert "errors_7d" in report
        assert "top_sources" in report
        assert "ctr_estimate" in report
        mgr.close()

    def test_empty_stats(self, tmp_db_path):
        mgr = AnalyticsManager(db_path=tmp_db_path)
        stats = mgr.get_delivery_stats(hours=24)
        assert stats == {
            "total_sent": 0,
            "delivered": 0,
            "delivery_rate": 0.0,
            "with_image": 0,
            "fallback_images": 0,
        }
        errors = mgr.get_error_stats(hours=24)
        assert errors == {
            "total_errors": 0,
            "flood_wait": 0,
            "retry_after": 0,
            "api_errors": 0,
            "network_errors": 0,
        }
        mgr.close()
