"""
Тесты для AI-провайдера.
BUG-005: Проверка, что get_leaders_context() не дублируется.
"""

from unittest.mock import MagicMock, patch

import pytest

from ai_core.ai_provider import AIProvider
from ai_core.routerai_provider import RouterAIProvider


class TestAIProvider:
    def test_routerai_build_prompt_no_duplicate_leaders_call(self):
        """
        BUG-005: Проверяем, что _build_prompt не вызывает get_leaders_context
        (он должен вызываться только в analyze_news).
        """
        provider = RouterAIProvider(api_key="fake-key", model="deepseek/deepseek-chat")
        with patch("ai_core.routerai_provider.get_leaders_context") as mock_ctx:
            mock_ctx.return_value = "USA: President - Test"
            prompt = provider._build_prompt("Test title", "Test summary", 5)
            assert "Test title" in prompt
            # _build_prompt НЕ должен вызывать get_leaders_context
            mock_ctx.assert_not_called()

    def test_analyze_news_calls_leaders_once(self):
        """
        BUG-005: analyze_news должен вызывать get_leaders_context() ровно 1 раз.
        """
        provider = RouterAIProvider(api_key="fake-key", model="deepseek/deepseek-chat")
        with patch.object(provider, "_make_request") as mock_req, patch(
            "ai_core.routerai_provider.get_leaders_context"
        ) as mock_ctx:
            mock_ctx.return_value = "USA: President - Test"
            mock_req.return_value = {
                "choices": [{"message": {"content": "Test analysis"}}],
                "usage": {"total_tokens": 100, "prompt_tokens": 80, "completion_tokens": 20},
            }
            # Запускаем корутину
            import asyncio

            asyncio.run(provider.analyze_news("Title", "Summary", 5))
            assert (
                mock_ctx.call_count == 1
            ), f"BUG-005: get_leaders_context() called {mock_ctx.call_count} times, expected 1"

    def test_fallback_to_yandex_when_routerai_fails(self):
        """При недоступности RouterAI должен использоваться Yandex."""
        with patch.object(AIProvider, "__init__", lambda self: None):
            provider = AIProvider.__new__(AIProvider)
            provider.available = {"routerai": False, "yandex": True}
            provider.provider_priority = ["yandex"]
            provider.routerai = MagicMock()
            provider.routerai.available = False
            with patch.object(provider, "_yandex_analyze") as mock_yandex:
                mock_yandex.return_value = MagicMock(text="Yandex analysis", provider="yandex")
                import asyncio

                result = asyncio.run(provider.analyze_news("Title", "Summary"))
                assert result.provider == "yandex"
