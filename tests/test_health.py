"""
Tests for health-check module with external API probes (P1-004).
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.health import HealthChecker


class TestHealthChecker:
    def test_record_publish(self):
        hc = HealthChecker()
        assert hc.last_publish_time is None
        hc.record_publish()
        assert hc.last_publish_time is not None

    def test_record_error(self):
        hc = HealthChecker()
        assert hc.error_count == 0
        hc.record_error()
        assert hc.error_count == 1

    def test_get_status_initial(self):
        hc = HealthChecker()
        status = hc.get_status()
        assert status["healthy"] is True
        assert status["errors_last_hour"] == 0
        assert status["checks"]["silence"]["ok"] is True

    def test_get_status_too_many_errors(self):
        hc = HealthChecker()
        for _ in range(15):
            hc.record_error()
        status = hc.get_status()
        assert status["healthy"] is False
        assert status["checks"]["errors"]["ok"] is False

    def test_get_status_silence(self):
        hc = HealthChecker()
        hc.last_publish_time = datetime.now() - timedelta(minutes=45)
        status = hc.get_status()
        assert status["healthy"] is False
        assert status["checks"]["silence"]["ok"] is False


class TestExternalAPIProbes:
    """P1-004: Тесты probes внешних API."""

    @pytest.mark.asyncio
    async def test_probe_telegram_success(self):
        hc = HealthChecker()
        mock_bot = AsyncMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")
        hc.bot = mock_bot

        result = await hc._probe_telegram()
        assert result["ok"] is True
        assert result["username"] == "testbot"

    @pytest.mark.asyncio
    async def test_probe_telegram_failure(self):
        hc = HealthChecker()
        mock_bot = AsyncMock()
        mock_bot.get_me.side_effect = Exception("Connection refused")
        hc.bot = mock_bot

        result = await hc._probe_telegram()
        assert result["ok"] is False
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_probe_telegram_no_bot(self):
        hc = HealthChecker()
        result = await hc._probe_telegram()
        assert result["ok"] is False
        assert "not initialized" in result["error"]

    @pytest.mark.asyncio
    @patch("utils.health.httpx.AsyncClient")
    async def test_probe_routerai_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"ROUTERAI_API_KEY": "test-key"}):
            hc = HealthChecker()
            result = await hc._probe_routerai()
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_probe_routerai_no_key(self):
        with patch.dict("os.environ", {"ROUTERAI_API_KEY": ""}, clear=False):
            hc = HealthChecker()
            result = await hc._probe_routerai()
            assert result["ok"] is False
            assert "not configured" in result["error"]

    @pytest.mark.asyncio
    @patch("utils.health.httpx.AsyncClient")
    async def test_probe_yandex_translate_no_creds(self, mock_client_cls):
        with patch.dict("os.environ", {"YANDEX_API_KEY": "", "YANDEX_FOLDER_ID": ""}, clear=False):
            hc = HealthChecker()
            result = await hc._probe_yandex_translate()
            assert result["ok"] is False
            assert "Credentials not configured" in result["error"]

    @pytest.mark.asyncio
    @patch("utils.health.httpx.AsyncClient")
    async def test_probe_searxng_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 404  # 404 тоже ок

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        hc = HealthChecker()
        result = await hc._probe_searxng()
        assert result["ok"] is True

    @pytest.mark.asyncio
    @patch("utils.health.httpx.AsyncClient")
    async def test_probe_searxng_connection_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        hc = HealthChecker()
        result = await hc._probe_searxng()
        assert result["ok"] is False
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_api_status_caching(self):
        """Результаты probes кэшируются на 60 секунд."""
        hc = HealthChecker()
        hc._api_status_cache = {"telegram": {"ok": True}}
        hc._api_cache_time = datetime.now()

        # Не должно быть новых запросов — вернётся кэш
        with patch.object(hc, "_probe_telegram") as mock_probe:
            result = await hc._check_external_apis()
            mock_probe.assert_not_called()
            assert result["telegram"]["ok"] is True

    @pytest.mark.asyncio
    async def test_get_full_status_includes_api_checks(self):
        hc = HealthChecker()
        hc._api_status_cache = {
            "telegram": {"ok": True},
            "routerai": {"ok": False, "error": "timeout"},
        }
        hc._api_cache_time = datetime.now()

        status = await hc.get_full_status()
        assert "api_checks" in status
        assert status["api_checks"]["telegram"]["ok"] is True
        assert status["api_checks"]["routerai"]["ok"] is False
        # Если API недоступен — статус нездоров
        assert status["healthy"] is False
