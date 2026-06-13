"""
Безопасность webhook-эндпоинта.
P0-001: Защита от spoofing через secret token и IP-whitelist.
"""

import ipaddress
import logging
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# Официальные IP-диапазоны Telegram Bot API
# https://core.telegram.org/resources/cidr.txt
_TELEGRAM_IP_RANGES = [
    ipaddress.ip_network("149.154.160.0/20"),
    ipaddress.ip_network("91.108.4.0/22"),
]


def _get_webhook_secret() -> Optional[str]:
    """Возвращает webhook secret из конфигурации."""
    return getattr(config, "WEBHOOK_SECRET", None)


def validate_webhook_request(request) -> tuple[bool, str]:
    """
    Проверяет входящий webhook-запрос на валидность.

    Returns:
        (is_valid, reason)
        is_valid: True если запрос прошёл все проверки
        reason: описание причины отказа (пустая строка если is_valid)
    """
    # 1. Проверка Content-Type
    content_type = request.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        return False, f"Invalid Content-Type: {content_type}"

    # 2. Проверка X-Telegram-Bot-Api-Secret-Token
    secret = _get_webhook_secret()
    if secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != secret:
            logger.warning(
                "Webhook: invalid secret token (header present=%s)",
                bool(header_secret),
            )
            return False, "Invalid secret token"

    # 3. Проверка IP-адреса источника
    # aiohttp предоставляет peername через transport
    peername = None
    if hasattr(request, "transport") and request.transport:
        peername = request.transport.get_extra_info("peername")
    elif hasattr(request, "remote"):
        # Fallback для разных версий aiohttp
        peername = (request.remote, 0)

    if peername and isinstance(peername, (tuple, list)) and len(peername) >= 1:
        client_ip = peername[0]
        if client_ip and not _is_telegram_ip(client_ip):
            # Если secret token валиден, но IP не из Telegram — это подозрительно,
            # но не критично если secret token настроен (Telegram рекомендует оба метода)
            # Однако если secret token НЕ настроен — IP-фильтр обязателен
            if not secret:
                logger.warning("Webhook: request from non-Telegram IP: %s", client_ip)
                return False, f"Unauthorized IP: {client_ip}"
            # Если secret token настроен, логируем но пропускаем
            # (например, reverse proxy может менять IP)
            logger.debug("Webhook: request from non-Telegram IP %s (secret token ok)", client_ip)

    return True, ""


def _is_telegram_ip(ip_str: str) -> bool:
    """Проверяет, принадлежит ли IP одному из диапазонов Telegram."""
    try:
        addr = ipaddress.ip_address(ip_str)
        for network in _TELEGRAM_IP_RANGES:
            if addr in network:
                return True
        return False
    except ValueError:
        logger.warning("Webhook: cannot parse IP address: %s", ip_str)
        return False


def get_telegram_ip_ranges() -> list[str]:
    """Возвращает список IP-диапазонов Telegram для документации."""
    return [str(net) for net in _TELEGRAM_IP_RANGES]
