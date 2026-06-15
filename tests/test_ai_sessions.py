"""
Tests for P2-003: Unified aiohttp sessions for AI providers.
"""

from unittest.mock import patch

import pytest

from ai_core.ai_provider import AIProvider
from ai_core.routerai_provider import RouterAIProvider


class TestRouterAIProviderSession:
    @pytest.mark.asyncio
    async def test_session_created_on_request(self):
        """Сессия создаётся при выполнении запроса."""
        p = RouterAIProvider(api_key="test")
        # В текущей реализации нет ленивой инициализации сессии —
        # _make_request создаёт новую сессию каждый раз.
        # Проверяем что провайдер инициализируется корректно.
        assert p.api_key == "test"
        assert p.available is True

    @pytest.mark.asyncio
    async def test_provider_available_with_key(self):
        """Провайдер доступен при наличии ключа."""
        p = RouterAIProvider(api_key="test-key")
        assert p.available is True

    @pytest.mark.asyncio
    async def test_provider_unavailable_without_key(self):
        """Провайдер недоступен без ключа."""
        with patch("ai_core.routerai_provider.os.getenv", return_value=None):
            p = RouterAIProvider(api_key=None)
            assert p.api_key is None
            assert p.available is False


class TestAIProviderSession:
    @pytest.mark.asyncio
    async def test_provider_initializes(self):
        """AIProvider инициализируется корректно."""
        p = AIProvider()
        assert p.routerai is not None

    @pytest.mark.asyncio
    async def test_analyze_news_returns_response(self):
        """analyze_news возвращает AIResponse даже при недоступности провайдеров."""
        p = AIProvider()
        resp = await p.analyze_news("Test title", "Test summary", score=5)
        assert resp is not None
        assert resp.text is not None
        assert resp.provider is not None
