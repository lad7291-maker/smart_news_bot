"""
Тесты для AlertManager.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.alert_manager import AlertManager


class TestAlertManager:
    def test_init(self):
        am = AlertManager()
        assert am.bot is None
        assert am._flood_wait_count == 0

    def test_set_bot(self):
        am = AlertManager(admin_id=0)
        mock_bot = MagicMock()
        am.set_bot(mock_bot)
        assert am.bot is mock_bot

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        result = await am.send_alert("Test alert", alert_type="test", cooldown_seconds=0)
        assert result is True
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 123
        assert "Test alert" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_alert_no_bot(self):
        am = AlertManager(admin_id=123)
        result = await am.send_alert("Test alert", cooldown_seconds=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_cooldown(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        # Первый алерт отправляется
        result1 = await am.send_alert("Alert 1", alert_type="same", cooldown_seconds=3600)
        assert result1 is True

        # Второй в пределах cooldown — не отправляется
        result2 = await am.send_alert("Alert 2", alert_type="same", cooldown_seconds=3600)
        assert result2 is False

        assert mock_bot.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_send_metric_alert(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        result = await am.send_metric_alert("rss_parse_latency_ms", 7000, 5000)
        assert result is True
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert "rss_parse_latency_ms" in call_kwargs["text"]
        assert "7000" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_ai_cost_alert(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        result = await am.send_ai_cost_alert(15.5, 10.0)
        assert result is True
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert "AI COST ALERT" in call_kwargs["text"]
        assert "$15.50" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_flood_wait_alert_below_threshold(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        # Меньше порога — не отправляется
        result = await am.send_flood_wait_alert(10)
        assert result is False
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_flood_wait_alert_above_threshold(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        result = await am.send_flood_wait_alert(60, article_title="Test Article")
        assert result is True
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert "FLOOD_WAIT ALERT" in call_kwargs["text"]
        assert "60" in call_kwargs["text"]
        assert "Test Article" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_flood_wait_alert_cooldown(self):
        am = AlertManager(admin_id=123)
        mock_bot = AsyncMock()
        am.set_bot(mock_bot)

        result1 = await am.send_flood_wait_alert(60)
        assert result1 is True

        # Второй в пределах cooldown
        result2 = await am.send_flood_wait_alert(60)
        assert result2 is False

        assert mock_bot.send_message.call_count == 1

    def test_reset(self):
        am = AlertManager(admin_id=123)
        am._flood_wait_count = 5
        am._last_flood_alert = time.time()
        am._get_state("test", 60)

        am.reset()
        assert am._flood_wait_count == 0
        assert am._last_flood_alert == 0.0
        assert len(am._states) == 0
