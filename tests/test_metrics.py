"""
Тесты для P2-004: Метрики latency и queue depth.

Покрывают:
- MetricsCollector: запись, агрегация p50/p95/p99
- Скользящее окно (старые данные отбрасываются)
- Алерты при превышении порогов
- get_report_text()
- timed() декоратор
"""

import asyncio
import time

import pytest

from utils.metrics import ALERT_THRESHOLDS_MS, MetricsCollector, _MetricSeries, collector, timed


class TestMetricSeries:
    """Тесты внутренней серии метрик."""

    def test_record_and_snapshot(self):
        s = _MetricSeries(window_seconds=60)
        s.record(10.0)
        s.record(20.0)
        s.record(30.0)
        assert s.snapshot() == [10.0, 20.0, 30.0]

    def test_p50(self):
        s = _MetricSeries(window_seconds=60)
        for v in [10, 20, 30, 40, 50]:
            s.record(float(v))
        assert s.p50() == 30.0

    def test_p95(self):
        s = _MetricSeries(window_seconds=60)
        for i in range(100):
            s.record(float(i))
        # p95 из 100 элементов = индекс 95 → значение 95
        assert s.p95() == 95.0

    def test_p99(self):
        s = _MetricSeries(window_seconds=60)
        for i in range(100):
            s.record(float(i))
        assert s.p99() == 99.0

    def test_empty_series(self):
        s = _MetricSeries(window_seconds=60)
        assert s.p50() is None
        assert s.p95() is None
        assert s.p99() is None
        assert s.count() == 0

    def test_sliding_window_expires_old(self):
        s = _MetricSeries(window_seconds=0.1)
        s.record(10.0)
        time.sleep(0.15)
        s.record(20.0)
        # Первое значение должно истечь
        assert s.snapshot() == [20.0]

    def test_count(self):
        s = _MetricSeries(window_seconds=60)
        assert s.count() == 0
        s.record(1.0)
        assert s.count() == 1
        s.record(2.0)
        assert s.count() == 2


class TestMetricsCollector:
    """Тесты сборщика метрик."""

    def test_record_latency(self):
        c = MetricsCollector(window_seconds=60)
        c.record_latency("test_metric", 100.0)
        c.record_latency("test_metric", 200.0)
        summary = c.get_summary()
        assert summary["test_metric"]["count"] == 2
        assert summary["test_metric"]["p50"] == 150.0

    def test_record_latency_from(self):
        c = MetricsCollector(window_seconds=60)
        start = time.time() - 0.1  # 100ms назад
        c.record_latency_from("test_metric", start)
        summary = c.get_summary()
        assert summary["test_metric"]["count"] == 1
        # Должно быть ~100ms ±50ms
        p50 = summary["test_metric"]["p50"]
        assert 50 <= p50 <= 200

    def test_set_queue_length(self):
        c = MetricsCollector(window_seconds=60)
        c.set_queue_length(5)
        c.set_queue_length(10)
        summary = c.get_summary()
        assert summary["scheduler_queue_length"]["count"] == 2

    def test_multiple_metrics(self):
        c = MetricsCollector(window_seconds=60)
        c.record_latency("rss_parse_latency_ms", 100.0)
        c.record_latency("ai_analysis_latency_ms", 500.0)
        c.record_latency("image_search_latency_ms", 200.0)
        summary = c.get_summary()
        assert len(summary) == 3
        assert summary["rss_parse_latency_ms"]["p50"] == 100.0
        assert summary["ai_analysis_latency_ms"]["p50"] == 500.0

    def test_reset(self):
        c = MetricsCollector(window_seconds=60)
        c.record_latency("test", 100.0)
        c.reset()
        summary = c.get_summary()
        assert summary == {}

    def test_report_text_empty(self):
        c = MetricsCollector(window_seconds=60)
        text = c.get_report_text()
        assert "Нет метрик" in text

    def test_report_text_with_data(self):
        c = MetricsCollector(window_seconds=60)
        c.record_latency("rss_parse_latency_ms", 100.0)
        c.record_latency("rss_parse_latency_ms", 200.0)
        text = c.get_report_text()
        assert "rss_parse_latency_ms" in text
        assert "p50" in text
        assert "p95" in text
        assert "p99" in text
        assert "n=2" in text

    def test_report_text_queue(self):
        c = MetricsCollector(window_seconds=60)
        c.set_queue_length(7)
        text = c.get_report_text()
        assert "scheduler_queue_length" in text


class TestAlerting:
    """Тесты алертов при превышении порогов."""

    def test_alert_fires_when_threshold_exceeded(self, caplog):
        c = MetricsCollector(window_seconds=60)
        c._alert_cooldown_seconds = 0  # убираем кулдаун для теста
        # ai_analysis порог = 30000ms
        c.record_latency("ai_analysis_latency_ms", 50000.0)
        assert "METRIC ALERT" in caplog.text
        assert "ai_analysis_latency_ms" in caplog.text

    def test_alert_not_fires_when_below_threshold(self, caplog):
        c = MetricsCollector(window_seconds=60)
        c._alert_cooldown_seconds = 0
        c.record_latency("ai_analysis_latency_ms", 1000.0)
        assert "METRIC ALERT" not in caplog.text

    def test_alert_respects_cooldown(self, caplog):
        c = MetricsCollector(window_seconds=60)
        c._alert_cooldown_seconds = 3600  # 1 час
        c.record_latency("ai_analysis_latency_ms", 50000.0)
        assert "METRIC ALERT" in caplog.text

        # Второй вызов в пределах кулдауна — алерта не должно быть
        caplog.clear()
        c.record_latency("ai_analysis_latency_ms", 60000.0)
        assert "METRIC ALERT" not in caplog.text

    def test_alert_only_for_configured_thresholds(self, caplog):
        c = MetricsCollector(window_seconds=60)
        c._alert_cooldown_seconds = 0
        c.record_latency("unknown_metric", 999999.0)
        assert "METRIC ALERT" not in caplog.text


class TestTimedDecorator:
    """Тесты декоратора @timed()."""

    def test_timed_sync_function(self):
        c = MetricsCollector(window_seconds=60)

        @timed("sync_test")
        def slow_func():
            time.sleep(0.05)
            return 42

        result = slow_func()
        assert result == 42
        # Метрика должна быть записана
        summary = collector.get_summary()
        assert "sync_test" in summary

    @pytest.mark.asyncio
    async def test_timed_async_function(self):
        @timed("async_test")
        async def slow_async():
            await asyncio.sleep(0.05)
            return "ok"

        result = await slow_async()
        assert result == "ok"
        summary = collector.get_summary()
        assert "async_test" in summary

    def test_timed_exception_still_records(self):
        @timed("exception_test")
        def failing_func():
            time.sleep(0.02)
            raise ValueError("boom")

        with pytest.raises(ValueError):
            failing_func()
        summary = collector.get_summary()
        assert "exception_test" in summary


class TestGlobalCollector:
    """Тесты глобального singleton."""

    def test_global_collector_exists(self):
        assert collector is not None
        collector.reset()
        collector.record_latency("global_test", 50.0)
        summary = collector.get_summary()
        assert "global_test" in summary
