"""
Circuit Breaker для внешних API (AI, переводчик).
P1-003: Защита от каскадных ошибок при недоступности API.

Состояния:
- CLOSED: нормальная работа, запросы проходят
- OPEN: после N ошибок подряд, запросы блокируются на timeout секунд
- HALF_OPEN: после timeout, один пробный запрос — при успехе CLOSED, при ошибке OPEN
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

from utils.logger import logger

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(str, Enum):
    CLOSED = "closed"  # Нормальная работа
    OPEN = "open"  # Блокировка
    HALF_OPEN = "half_open"  # Пробный запрос


@dataclass
class CircuitBreakerConfig:
    """Конфигурация circuit breaker."""

    failure_threshold: int = 3  # Ошибок подряд для OPEN
    recovery_timeout: int = 300  # Секунд до HALF_OPEN (5 мин)
    half_open_max_calls: int = 1  # Пробных запросов в HALF_OPEN
    expected_exception: type = Exception  # Какие исключения считать ошибками


@dataclass
class CircuitBreakerStats:
    """Статистика circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0


class APICircuitBreaker:
    """
    Circuit breaker для async функций.

    Usage:
        cb = APICircuitBreaker("routerai", failure_threshold=3, recovery_timeout=300)

        @cb.protect(fallback="AI analysis temporarily unavailable.")
        async def analyze_news(...):
            ...
    """

    _instances: Dict[str, "APICircuitBreaker"] = {}
    _lock = asyncio.Lock()

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 300,
        half_open_max_calls: int = 1,
        expected_exception: type = Exception,
    ):
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exception=expected_exception,
        )
        self.stats = CircuitBreakerStats()
        self._state_lock = asyncio.Lock()
        logger.info(
            f"🔒 CircuitBreaker '{name}' initialized: threshold={failure_threshold}, timeout={recovery_timeout}s"
        )

    @classmethod
    def get_instance(cls, name: str, **kwargs) -> "APICircuitBreaker":
        """Возвращает существующий или создаёт новый circuit breaker."""
        if name not in cls._instances:
            cls._instances[name] = cls(name, **kwargs)
        return cls._instances[name]

    @classmethod
    def reset_all(cls) -> None:
        """Сбрасывает все circuit breakers (для тестов)."""
        cls._instances.clear()

    async def call(self, func: Callable, fallback: Any, *args, **kwargs) -> Any:
        """
        Вызывает функцию с защитой circuit breaker.

        Args:
            func: Async функция для вызова
            fallback: Значение при OPEN или ошибке
            *args, **kwargs: Аргументы для func
        """
        async with self._state_lock:
            await self._transition_state()

            if self.stats.state == CircuitState.OPEN:
                logger.warning(f"🔒 CircuitBreaker '{self.name}' is OPEN — returning fallback")
                return fallback

            if self.stats.state == CircuitState.HALF_OPEN:
                if self.stats.half_open_calls >= self.config.half_open_max_calls:
                    logger.warning(
                        f"🔒 CircuitBreaker '{self.name}' HALF_OPEN limit reached — returning fallback"
                    )
                    return fallback
                self.stats.half_open_calls += 1

        # Выполняем запрос (вне lock, чтобы не блокировать другие)
        self.stats.total_calls += 1
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except self.config.expected_exception as e:
            await self._record_failure()
            logger.warning(f"🔒 CircuitBreaker '{self.name}' call failed: {e}")
            return fallback

    async def _transition_state(self) -> None:
        """Проверяет и обновляет состояние по таймауту."""
        if self.stats.state == CircuitState.OPEN:
            if self.stats.last_failure_time:
                elapsed = (datetime.now() - self.stats.last_failure_time).total_seconds()
                if elapsed >= self.config.recovery_timeout:
                    logger.info(f"🔒 CircuitBreaker '{self.name}' → HALF_OPEN (timeout expired)")
                    self.stats.state = CircuitState.HALF_OPEN
                    self.stats.half_open_calls = 0

    async def _record_success(self) -> None:
        """Записывает успешный вызов."""
        async with self._state_lock:
            self.stats.successes += 1
            self.stats.total_successes += 1
            self.stats.last_success_time = datetime.now()

            if self.stats.state == CircuitState.HALF_OPEN:
                logger.info(f"🔒 CircuitBreaker '{self.name}' → CLOSED (recovery successful)")
                self.stats.state = CircuitState.CLOSED
                self.stats.failures = 0
                self.stats.half_open_calls = 0
            else:
                # В CLOSED — сбрасываем счётчик ошибок
                if self.stats.failures > 0:
                    self.stats.failures = 0

    async def _record_failure(self) -> None:
        """Записывает неудачный вызов."""
        async with self._state_lock:
            self.stats.failures += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = datetime.now()

            if self.stats.failures >= self.config.failure_threshold:
                if self.stats.state != CircuitState.OPEN:
                    logger.warning(
                        f"🔒 CircuitBreaker '{self.name}' → OPEN "
                        f"({self.stats.failures}/{self.config.failure_threshold} failures)"
                    )
                self.stats.state = CircuitState.OPEN
                self.stats.half_open_calls = 0

    def protect(self, fallback: Any) -> Callable[[F], F]:
        """
        Декоратор для защиты async функции.

        Usage:
            @cb.protect(fallback="default text")
            async def my_func():
                ...
        """

        def decorator(func: F) -> F:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await self.call(func, fallback, *args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorator

    def get_status(self) -> Dict[str, Any]:
        """Возвращает текущий статус для мониторинга."""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "failures": self.stats.failures,
            "successes": self.stats.successes,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "last_failure": (
                self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None
            ),
            "last_success": (
                self.stats.last_success_time.isoformat() if self.stats.last_success_time else None
            ),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
            },
        }
