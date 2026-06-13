"""
Тесты для Circuit Breaker RSS-источников.
P0-003: Graceful degradation RSS-источников.
"""

from datetime import datetime, timedelta

import pytest

from utils.circuit_breaker import SourceHealth, SourceHealthTracker, SourceStatus


class TestCircuitBreaker:
    def test_init_creates_table(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        statuses = tracker.get_all_statuses()
        assert isinstance(statuses, list)
        tracker.close()

    def test_can_use_new_source(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        assert tracker.can_use("TestSource", "https://example.com/rss") is True
        tracker.close()

    def test_record_success_clears_errors(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        tracker.record_error("Src", "https://example.com/rss", "timeout")
        tracker.record_error("Src", "https://example.com/rss", "timeout")
        assert tracker.get_all_statuses()[0]["consecutive_errors"] == 2

        tracker.record_success("Src", "https://example.com/rss")
        assert tracker.get_all_statuses()[0]["consecutive_errors"] == 0
        assert tracker.get_all_statuses()[0]["status"] == "ok"
        tracker.close()

    def test_degraded_after_three_errors(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        for _ in range(3):
            tracker.record_error("Fragile", "https://example.com/rss", "timeout")

        status = tracker.get_all_statuses()[0]
        assert status["status"] == "degraded"
        assert status["consecutive_errors"] == 3
        tracker.close()

    def test_cannot_use_degraded_source(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        for _ in range(3):
            tracker.record_error("Down", "https://example.com/rss", "timeout")

        assert tracker.can_use("Down", "https://example.com/rss") is False
        tracker.close()

    def test_degraded_source_recover_after_timeout(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        for _ in range(3):
            tracker.record_error("Recover", "https://example.com/rss", "timeout")

        assert tracker.can_use("Recover", "https://example.com/rss") is False

        # Имитируем прошедшее время — устанавливаем disabled_until в прошлое
        health = tracker._states["Recover"]
        health.disabled_until = datetime.now() - timedelta(minutes=1)
        tracker._save_state(health)

        assert tracker.can_use("Recover", "https://example.com/rss") is True
        assert tracker._states["Recover"].status == SourceStatus.OK
        tracker.close()

    def test_offline_after_degraded_errors(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        # 3 ошибки → DEGRADED
        for _ in range(3):
            tracker.record_error("Bad", "https://example.com/rss", "timeout")
        assert tracker._states["Bad"].status == SourceStatus.DEGRADED

        # Ещё 3 ошибки → OFFLINE
        for _ in range(3):
            tracker.record_error("Bad", "https://example.com/rss", "timeout")
        assert tracker._states["Bad"].status == SourceStatus.OFFLINE
        tracker.close()

    def test_response_time_tracking(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        tracker.record_success("Fast", "https://example.com/rss", response_ms=150.0)
        tracker.record_success("Fast", "https://example.com/rss", response_ms=200.0)

        status = tracker.get_all_statuses()[0]
        assert status["avg_response_ms"] is not None
        assert status["avg_response_ms"] > 0
        tracker.close()

    def test_total_requests_and_errors(self, tmp_db_path):
        tracker = SourceHealthTracker(db_path=tmp_db_path)
        tracker.record_success("Stats", "https://example.com/rss")
        tracker.record_success("Stats", "https://example.com/rss")
        tracker.record_error("Stats", "https://example.com/rss", "fail")

        status = tracker.get_all_statuses()[0]
        assert status["total_requests"] == 3
        assert status["total_errors"] == 1
        tracker.close()

    def test_persistence_across_instances(self, tmp_db_path):
        tracker1 = SourceHealthTracker(db_path=tmp_db_path)
        tracker1.record_error("Persist", "https://example.com/rss", "fail")
        tracker1.close()

        tracker2 = SourceHealthTracker(db_path=tmp_db_path)
        statuses = tracker2.get_all_statuses()
        persist = [s for s in statuses if s["source_tag"] == "Persist"]
        assert len(persist) == 1
        assert persist[0]["total_errors"] == 1
        tracker2.close()
