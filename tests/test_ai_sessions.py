"""
Tests for P2-003: Unified aiohttp sessions for AI providers.
"""

import pytest

from ai_core.ai_provider import AIProvider
from ai_core.routerai_provider import RouterAIProvider


class TestRouterAIProviderSession:
    @pytest.mark.asyncio
    async def test_session_lazy_init(self):
        """Сессия создаётся лениво при первом обращении."""
        p = RouterAIProvider(api_key="test")
        assert p._session is None
        s = p.session
        assert s is not None
        assert not s.closed
        await p.close()

    @pytest.mark.asyncio
    async def test_session_reused(self):
        """Сессия переиспользуется между обращениями."""
        p = RouterAIProvider(api_key="test")
        s1 = p.session
        s2 = p.session
        assert s1 is s2
        await p.close()

    @pytest.mark.asyncio
    async def test_session_closed_on_close(self):
        """Сессия закрывается при вызове close()."""
        p = RouterAIProvider(api_key="test")
        s = p.session
        await p.close()
        assert s.closed
        assert p._session is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Повторный close() не падает."""
        p = RouterAIProvider(api_key="test")
        await p.close()
        await p.close()  # should not raise

    @pytest.mark.asyncio
    async def test_session_recreated_after_close(self):
        """Сессия пересоздаётся после закрытия."""
        p = RouterAIProvider(api_key="test")
        s1 = p.session
        await p.close()
        s2 = p.session
        assert s2 is not s1
        assert not s2.closed
        await p.close()


class TestAIProviderSession:
    @pytest.mark.asyncio
    async def test_sessions_lazy_init(self):
        """Обе сессии создаются лениво."""
        p = AIProvider()
        assert p._session is None
        assert p.routerai._session is None
        s = p.session
        assert s is not None
        assert not s.closed
        await p.close()

    @pytest.mark.asyncio
    async def test_close_closes_both_sessions(self):
        """close() закрывает и свою сессию, и routerai."""
        p = AIProvider()
        ps = p.session
        rs = p.routerai.session
        await p.close()
        assert ps.closed
        assert rs.closed

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Повторный close() не падает."""
        p = AIProvider()
        await p.close()
        await p.close()
