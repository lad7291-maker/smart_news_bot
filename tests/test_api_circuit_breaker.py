"""
Tests for API Circuit Breaker (P1-003).
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from utils.api_circuit_breaker import APICircuitBreaker, CircuitState


class TestAPICircuitBreaker:
    def setup_method(self):
        """Сбрасываем все circuit breakers перед каждым тестом."""
        APICircuitBreaker.reset_all()

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self):
        cb = APICircuitBreaker.get_instance("test1", failure_threshold=3, recovery_timeout=1)
        assert cb.stats.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_keeps_closed(self):
        cb = APICircuitBreaker.get_instance("test2", failure_threshold=3, recovery_timeout=1)
        mock_func = AsyncMock(return_value="ok")
        result = await cb.call(mock_func, fallback="fallback")
        assert result == "ok"
        assert cb.stats.state == CircuitState.CLOSED
        assert cb.stats.total_successes == 1

    @pytest.mark.asyncio
    async def test_failure_counts_towards_open(self):
        cb = APICircuitBreaker.get_instance("test3", failure_threshold=3, recovery_timeout=1)
        mock_func = AsyncMock(side_effect=Exception("fail"))

        # 1 ошибка — ещё CLOSED
        result = await cb.call(mock_func, fallback="fallback")
        assert result == "fallback"
        assert cb.stats.state == CircuitState.CLOSED
        assert cb.stats.failures == 1

        # 2 ошибки — ещё CLOSED
        result = await cb.call(mock_func, fallback="fallback")
        assert cb.stats.state == CircuitState.CLOSED
        assert cb.stats.failures == 2

        # 3 ошибки — OPEN
        result = await cb.call(mock_func, fallback="fallback")
        assert cb.stats.state == CircuitState.OPEN
        assert cb.stats.failures == 3

    @pytest.mark.asyncio
    async def test_open_returns_fallback_immediately(self):
        cb = APICircuitBreaker.get_instance("test4", failure_threshold=2, recovery_timeout=60)
        mock_func = AsyncMock(side_effect=Exception("fail"))

        # Доводим до OPEN
        await cb.call(mock_func, fallback="fallback")
        await cb.call(mock_func, fallback="fallback")
        assert cb.stats.state == CircuitState.OPEN

        # При OPEN функция не вызывается, сразу fallback
        mock_func.reset_mock()
        result = await cb.call(mock_func, fallback="fallback")
        assert result == "fallback"
        assert mock_func.call_count == 0  # Не вызвана!

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        cb = APICircuitBreaker.get_instance("test5", failure_threshold=2, recovery_timeout=0)
        mock_func = AsyncMock(side_effect=Exception("fail"))

        # Доводим до OPEN
        await cb.call(mock_func, fallback="fallback")
        await cb.call(mock_func, fallback="fallback")
        assert cb.stats.state == CircuitState.OPEN

        # Ждём timeout (0 секунд — сразу)
        await asyncio.sleep(0.1)

        # Пробный запрос в HALF_OPEN
        mock_func.reset_mock(side_effect=True)
        mock_func.return_value = "recovery"
        result = await cb.call(mock_func, fallback="fallback")
        assert result == "recovery"
        assert cb.stats.state == CircuitState.CLOSED  # Восстановились!

    @pytest.mark.asyncio
    async def test_half_open_failure_returns_to_open(self):
        cb = APICircuitBreaker.get_instance("test6", failure_threshold=2, recovery_timeout=0)
        mock_func = AsyncMock(side_effect=Exception("fail"))

        # Доводим до OPEN
        await cb.call(mock_func, fallback="fallback")
        await cb.call(mock_func, fallback="fallback")
        assert cb.stats.state == CircuitState.OPEN

        await asyncio.sleep(0.1)

        # Пробный запрос в HALF_OPEN — снова ошибка
        result = await cb.call(mock_func, fallback="fallback")
        assert result == "fallback"
        assert cb.stats.state == CircuitState.OPEN  # Остались в OPEN

    @pytest.mark.asyncio
    async def test_success_resets_failures(self):
        cb = APICircuitBreaker.get_instance("test7", failure_threshold=3, recovery_timeout=60)

        # 2 ошибки
        fail_func = AsyncMock(side_effect=Exception("fail"))
        await cb.call(fail_func, fallback="fallback")
        await cb.call(fail_func, fallback="fallback")
        assert cb.stats.failures == 2

        # Успех — сбрасывает счётчик
        ok_func = AsyncMock(return_value="ok")
        await cb.call(ok_func, fallback="fallback")
        assert cb.stats.failures == 0
        assert cb.stats.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_protect_decorator(self):
        cb = APICircuitBreaker.get_instance("test8", failure_threshold=2, recovery_timeout=60)

        @cb.protect(fallback="decorated_fallback")
        async def my_func(should_fail: bool = False):
            if should_fail:
                raise Exception("fail")
            return "success"

        # Успешный вызов
        result = await my_func(should_fail=False)
        assert result == "success"

        # 2 ошибки — OPEN
        await my_func(should_fail=True)
        await my_func(should_fail=True)

        # При OPEN — fallback
        result = await my_func(should_fail=False)
        assert result == "decorated_fallback"

    @pytest.mark.asyncio
    async def test_get_status(self):
        cb = APICircuitBreaker.get_instance("test9", failure_threshold=3, recovery_timeout=60)
        status = cb.get_status()
        assert status["name"] == "test9"
        assert status["state"] == "closed"
        assert status["config"]["failure_threshold"] == 3
        assert status["config"]["recovery_timeout"] == 60
