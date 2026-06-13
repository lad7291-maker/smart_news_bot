"""
P2-004: In-memory метрики latency и queue depth.

Собирает:
- rss_parse_latency_ms
- ai_analysis_latency_ms
- image_search_latency_ms
- telegram_send_latency_ms
- scheduler_queue_length
- sqlite_write_latency_ms

Агрегация: p50, p95, p99 за скользящее окно (по умолчанию 5 мин).
Алерты: при p95 > threshold отправляется warning в лог.
"""

import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional

from utils.alert_manager import alert_manager
from utils.logger import logger

# Пороги алертов (мс)
ALERT_THRESHOLDS_MS = {
    "rss_parse_latency_ms": 5000,
    "ai_analysis_latency_ms": 30000,
    "image_search_latency_ms": 10000,
    "telegram_send_latency_ms": 5000,
    "sqlite_write_latency_ms": 1000,
}

# Скользящее окно (сек)
DEFAULT_WINDOW_SECONDS = 300


@dataclass
class _MetricSeries:
    """Одна временная серия: deque из (timestamp, value)."""

    window_seconds: float
    data: Deque[tuple] = field(default_factory=lambda: deque())

    def record(self, value: float) -> None:
        now = time.time()
        self.data.append((now, value))
        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.data and self.data[0][0] < cutoff:
            self.data.popleft()

    def snapshot(self) -> List[float]:
        now = time.time()
        self._trim(now)
        return [v for _, v in self.data]

    def count(self) -> int:
        return len(self.snapshot())

    def p50(self) -> Optional[float]:
        vals = self.snapshot()
        if not vals:
            return None
        return statistics.median(vals)

    def p95(self) -> Optional[float]:
        vals = sorted(self.snapshot())
        if not vals:
            return None
        idx = int(len(vals) * 0.95)
        if idx >= len(vals):
            idx = len(vals) - 1
        return vals[idx]

    def p99(self) -> Optional[float]:
        vals = sorted(self.snapshot())
        if not vals:
            return None
        idx = int(len(vals) * 0.99)
        if idx >= len(vals):
            idx = len(vals) - 1
        return vals[idx]


class MetricsCollector:
    """Сборщик метрик с in-memory histogram."""

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._series: Dict[str, _MetricSeries] = {}
        self._queue_length: int = 0
        self._last_alert_time: Dict[str, float] = {}
        self._alert_cooldown_seconds = 300  # не алертить чаще 5 мин

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _get_series(self, name: str) -> _MetricSeries:
        if name not in self._series:
            self._series[name] = _MetricSeries(window_seconds=self._window)
        return self._series[name]

    def record_latency(self, name: str, latency_ms: float) -> None:
        """Записать latency в миллисекундах."""
        series = self._get_series(name)
        series.record(latency_ms)
        self._check_alert(name, latency_ms)

    def record_latency_from(self, name: str, start_time: float) -> None:
        """Удобная обёртка: start_time = time.time() перед операцией."""
        latency_ms = (time.time() - start_time) * 1000
        self.record_latency(name, latency_ms)

    def set_queue_length(self, length: int) -> None:
        """Установить текущую длину очереди."""
        self._queue_length = length
        self._get_series("scheduler_queue_length").record(float(length))

    # ------------------------------------------------------------------
    # Alerting
    # ------------------------------------------------------------------

    def _check_alert(self, name: str, latency_ms: float) -> None:
        threshold = ALERT_THRESHOLDS_MS.get(name)
        if not threshold:
            return
        if latency_ms < threshold:
            return

        now = time.time()
        last = self._last_alert_time.get(name, 0)
        if now - last < self._alert_cooldown_seconds:
            return

        self._last_alert_time[name] = now
        logger.warning(
            f"🚨 METRIC ALERT: {name} p95 превышен. "
            f"Текущее значение: {latency_ms:.0f}ms, порог: {threshold}ms"
        )
        # Отправляем алерт в Telegram (async — fire-and-forget)
        try:
            asyncio.create_task(alert_manager.send_metric_alert(name, latency_ms, threshold))
        except Exception as e:
            logger.error(f"Failed to queue metric alert: {e}")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Dict[str, Optional[float]]]:
        """Возвращает сводку по всем метрикам."""
        result: Dict[str, Dict[str, Optional[float]]] = {}
        for name, series in self._series.items():
            result[name] = {
                "count": series.count(),
                "p50": series.p50(),
                "p95": series.p95(),
                "p99": series.p99(),
            }
        return result

    def get_report_text(self) -> str:
        """Форматирует отчёт для Telegram."""
        summary = self.get_summary()
        if not summary:
            return "📊 Нет метрик (слишком рано или нет данных)"

        lines = ["📊 <b>Метрики (за 5 мин)</b>\n"]
        for name in sorted(summary):
            s = summary[name]
            count = int(s["count"] or 0)
            if count == 0:
                continue
            p50 = s["p50"]
            p95 = s["p95"]
            p99 = s["p99"]

            # Форматируем единицы
            if "queue" in name:
                unit = ""
                fmt = ".0f"
            else:
                unit = "ms"
                fmt = ".0f"

            p50_str = f"{p50:{fmt}}{unit}" if p50 is not None else "N/A"
            p95_str = f"{p95:{fmt}}{unit}" if p95 is not None else "N/A"
            p99_str = f"{p99:{fmt}}{unit}" if p99 is not None else "N/A"

            lines.append(
                f"<b>{name}</b> (n={count})\n" f"  p50: {p50_str} | p95: {p95_str} | p99: {p99_str}"
            )

        if len(lines) == 1:
            return "📊 Нет метрик (слишком рано или нет данных)"

        return "\n".join(lines)

    def reset(self) -> None:
        """Сбросить все метрики."""
        self._series.clear()
        self._queue_length = 0
        self._last_alert_time.clear()


# Глобальный singleton
collector = MetricsCollector()


# ------------------------------------------------------------------
# Decorator for easy instrumentation
# ------------------------------------------------------------------


def timed(metric_name: str):
    """Декоратор для автоматического измерения latency функции."""

    def decorator(func: Callable) -> Callable:
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                collector.record_latency_from(metric_name, start)

        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                collector.record_latency_from(metric_name, start)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
