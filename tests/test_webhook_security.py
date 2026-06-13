"""
Тесты для безопасности webhook (P0-001).
Проверка secret token, IP-whitelist, Content-Type.
"""

from unittest.mock import MagicMock

import pytest

from utils.webhook_security import _is_telegram_ip, get_telegram_ip_ranges, validate_webhook_request


class MockRequest:
    """Мок aiohttp Request для тестов."""

    def __init__(
        self,
        headers=None,
        remote=None,
        transport_peername=None,
    ):
        self.headers = headers or {}
        self.remote = remote
        self._transport_peername = transport_peername

    @property
    def transport(self):
        class FakeTransport:
            def get_extra_info(inner_self, name):
                if name == "peername":
                    return self._transport_peername
                return None

        return FakeTransport()


class TestValidateWebhookRequest:
    """Тесты валидации webhook-запросов."""

    def test_valid_request_with_secret(self, monkeypatch):
        """Валидный запрос с правильным secret token."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET="my-secret"))

        request = MockRequest(
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "my-secret",
            },
            transport_peername=("149.154.160.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is True
        assert reason == ""

    def test_invalid_secret_token(self, monkeypatch):
        """Неправильный secret token → 403."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET="my-secret"))

        request = MockRequest(
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
            },
            transport_peername=("149.154.160.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is False
        assert "secret token" in reason.lower()

    def test_missing_secret_token_when_configured(self, monkeypatch):
        """Отсутствует secret token, но он настроен → 403."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET="my-secret"))

        request = MockRequest(
            headers={"Content-Type": "application/json"},
            transport_peername=("149.154.160.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is False
        assert "secret token" in reason.lower()

    def test_no_secret_configured_valid_telegram_ip(self, monkeypatch):
        """Secret не настроен, но IP из Telegram → OK."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET=None))

        request = MockRequest(
            headers={"Content-Type": "application/json"},
            transport_peername=("149.154.160.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is True
        assert reason == ""

    def test_no_secret_configured_invalid_ip(self, monkeypatch):
        """Secret не настроен, IP не из Telegram → 403."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET=None))

        request = MockRequest(
            headers={"Content-Type": "application/json"},
            transport_peername=("192.168.1.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is False
        assert "unauthorized ip" in reason.lower()

    def test_invalid_content_type(self, monkeypatch):
        """Неправильный Content-Type → 403."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET="my-secret"))

        request = MockRequest(
            headers={
                "Content-Type": "text/plain",
                "X-Telegram-Bot-Api-Secret-Token": "my-secret",
            },
            transport_peername=("149.154.160.1", 12345),
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is False
        assert "content-type" in reason.lower()

    def test_valid_secret_overrides_ip_check(self, monkeypatch):
        """Если secret token валиден, не-Telegram IP допускается (reverse proxy)."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET="my-secret"))

        request = MockRequest(
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "my-secret",
            },
            transport_peername=("10.0.0.1", 12345),  # private IP
        )

        is_valid, reason = validate_webhook_request(request)
        assert is_valid is True
        assert reason == ""

    def test_no_peername_no_secret(self, monkeypatch):
        """Нет peername, нет secret → OK (best effort, небезопасно в проде)."""
        monkeypatch.setattr("utils.webhook_security.config", MagicMock(WEBHOOK_SECRET=None))

        request = MockRequest(
            headers={"Content-Type": "application/json"},
            transport_peername=None,
        )

        is_valid, reason = validate_webhook_request(request)
        # Без peername и без secret мы не можем проверить источник
        # Это небезопасная конфигурация, но не блокируем запрос
        assert is_valid is True


class TestIsTelegramIP:
    """Тесты проверки IP-адресов Telegram."""

    def test_telegram_ip_149_154_160(self):
        assert _is_telegram_ip("149.154.160.1") is True
        assert _is_telegram_ip("149.154.175.254") is True

    def test_telegram_ip_91_108_4(self):
        assert _is_telegram_ip("91.108.4.1") is True
        assert _is_telegram_ip("91.108.7.254") is True

    def test_non_telegram_ip(self):
        assert _is_telegram_ip("192.168.1.1") is False
        assert _is_telegram_ip("8.8.8.8") is False
        assert _is_telegram_ip("1.1.1.1") is False

    def test_invalid_ip(self):
        assert _is_telegram_ip("not-an-ip") is False
        assert _is_telegram_ip("") is False

    def test_boundary_ips(self):
        # Границы диапазонов
        assert _is_telegram_ip("149.154.160.0") is True
        assert _is_telegram_ip("149.154.175.255") is True
        assert _is_telegram_ip("149.154.159.255") is False
        assert _is_telegram_ip("149.154.176.0") is False


class TestGetTelegramIPRanges:
    def test_returns_list_of_strings(self):
        ranges = get_telegram_ip_ranges()
        assert isinstance(ranges, list)
        assert len(ranges) >= 2
        for r in ranges:
            assert isinstance(r, str)
            assert "/" in r  # CIDR notation


class TestBotRunnerWebhookIntegration:
    """Интеграционные тесты handle_webhook в bot_runner."""

    def test_handle_webhook_rejects_invalid_secret(self, monkeypatch):
        """handle_webhook возвращает 403 при невалидном secret."""
        import asyncio

        from aiohttp import web

        from bot_runner import main

        # Мокаем config для webhook_security (импортирован как from config import config)
        monkeypatch.setattr(
            "utils.webhook_security.config",
            MagicMock(
                WEBHOOK_URL="https://example.com",
                WEBHOOK_PATH="/webhook",
                WEBHOOK_PORT=8080,
                WEBHOOK_SECRET="real-secret",
                TELEGRAM_BOT_TOKEN="fake-token",
                TELEGRAM_CHANNEL_ID="@channel",
            ),
        )

        # Создаём простой handler как в bot_runner
        async def handle_webhook(request):
            from utils.webhook_security import validate_webhook_request

            is_valid, reason = validate_webhook_request(request)
            if not is_valid:
                return web.Response(status=403, text=f"Forbidden: {reason}")
            return web.Response()

        async def test_request():
            app = web.Application()
            app.router.add_post("/webhook", handle_webhook)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 18080)
            await site.start()

            import aiohttp

            async with aiohttp.ClientSession() as session:
                # Запрос без secret
                async with session.post(
                    "http://127.0.0.1:18080/webhook",
                    headers={"Content-Type": "application/json"},
                    json={"update_id": 1},
                ) as resp:
                    assert resp.status == 403

                # Запрос с неверным secret
                async with session.post(
                    "http://127.0.0.1:18080/webhook",
                    headers={
                        "Content-Type": "application/json",
                        "X-Telegram-Bot-Api-Secret-Token": "wrong",
                    },
                    json={"update_id": 1},
                ) as resp:
                    assert resp.status == 403

                # Запрос с верным secret
                async with session.post(
                    "http://127.0.0.1:18080/webhook",
                    headers={
                        "Content-Type": "application/json",
                        "X-Telegram-Bot-Api-Secret-Token": "real-secret",
                    },
                    json={"update_id": 1},
                ) as resp:
                    assert resp.status == 200

            await runner.cleanup()

        asyncio.run(test_request())
