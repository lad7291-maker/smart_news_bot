"""
Унифицированный менеджер алертов для Smart News Bot.

Отправляет алерты админу в Telegram с cooldown и дедупликацией.
Поддерживает:
- Метрические алерты (latency)
- AI cost алерты
- FLOOD_WAIT алерты
- Health-check алерты (через health.py)
"""

import asyncio

# ID администратора для алертов
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from utils.logger import logger

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# Пороги для AI cost алерта
AI_COST_DAILY_BUDGET = float(os.getenv("AI_COST_DAILY_BUDGET", "10.0"))
AI_COST_ALERT_COOLDOWN_HOURS = 6

# Порог для FLOOD_WAIT алерта (сек)
FLOOD_WAIT_ALERT_THRESHOLD = 30
FLOOD_WAIT_ALERT_COOLDOWN_MINUTES = 15


@dataclass
class _AlertState:
    """Состояние одного типа алерта."""

    last_sent: float = 0.0
    cooldown_seconds: float = 300.0  # по умолчанию 5 мин
    sent_count: int = 0


class AlertManager:
    """Управляет отправкой алертов админу с cooldown."""

    def __init__(self, bot=None, admin_id: int = ADMIN_ID):
        self.bot = bot
        self.admin_id = admin_id
        self._states: Dict[str, _AlertState] = {}
        self._flood_wait_count: int = 0
        self._last_flood_alert: float = 0.0

    def set_bot(self, bot) -> None:
        """Устанавливает бота для отправки сообщений."""
        self.bot = bot

    def _get_state(self, alert_type: str, cooldown_seconds: float = 300.0) -> _AlertState:
        if alert_type not in self._states:
            self._states[alert_type] = _AlertState(cooldown_seconds=cooldown_seconds)
        return self._states[alert_type]

    def _can_send(self, state: _AlertState) -> bool:
        now = time.time()
        if now - state.last_sent < state.cooldown_seconds:
            return False
        state.last_sent = now
        state.sent_count += 1
        return True

    async def send_alert(
        self, text: str, alert_type: str = "generic", cooldown_seconds: float = 300.0
    ) -> bool:
        """Отправляет алерт админу с учётом cooldown.

        Returns:
            True если алерт был отправлен, False если в cooldown.
        """
        if not self.bot or not self.admin_id:
            logger.warning(
                f"Cannot send alert ({alert_type}): bot={self.bot is not None}, admin_id={self.admin_id}"
            )
            return False

        state = self._get_state(alert_type, cooldown_seconds)
        if not self._can_send(state):
            logger.debug(f"Alert {alert_type} in cooldown")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.admin_id,
                text=text,
                parse_mode="HTML",
            )
            logger.info(f"Alert sent ({alert_type}): {text[:80]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send alert ({alert_type}): {e}")
            return False

    # ------------------------------------------------------------------
    # Метрические алерты
    # ------------------------------------------------------------------

    async def send_metric_alert(
        self, metric_name: str, latency_ms: float, threshold_ms: float
    ) -> bool:
        """Отправляет алерт о превышении latency."""
        text = (
            f"🐌 <b>METRIC ALERT: {metric_name}</b>\n\n"
            f"Текущее значение: <code>{latency_ms:.0f}ms</code>\n"
            f"Порог: <code>{threshold_ms}ms</code>\n\n"
            f"<i>Используй /metrics для деталей</i>"
        )
        return await self.send_alert(text, alert_type=f"metric:{metric_name}", cooldown_seconds=300)

    # ------------------------------------------------------------------
    # AI Cost алерты
    # ------------------------------------------------------------------

    async def send_ai_cost_alert(self, spent: float, budget: float = AI_COST_DAILY_BUDGET) -> bool:
        """Отправляет алерт о превышении дневного бюджета AI."""
        text = (
            f"💸 <b>AI COST ALERT</b>\n\n"
            f"Потрачено: <code>${spent:.2f}</code> из <code>${budget:.2f}</code>\n"
            f"Превышен дневной лимит!\n\n"
            f"<i>Используй /ai_cost для деталей</i>"
        )
        return await self.send_alert(
            text, alert_type="ai_cost", cooldown_seconds=AI_COST_ALERT_COOLDOWN_HOURS * 3600
        )

    # ------------------------------------------------------------------
    # FLOOD_WAIT алерты
    # ------------------------------------------------------------------

    async def send_flood_wait_alert(
        self, retry_after: int, article_title: Optional[str] = None
    ) -> bool:
        """Отправляет алерт при значительном FLOOD_WAIT."""
        if retry_after < FLOOD_WAIT_ALERT_THRESHOLD:
            return False

        now = time.time()
        if now - self._last_flood_alert < FLOOD_WAIT_ALERT_COOLDOWN_MINUTES * 60:
            self._flood_wait_count += 1
            return False

        self._last_flood_alert = now
        self._flood_wait_count += 1

        title_part = f"\nСтатья: {article_title[:50]}..." if article_title else ""
        text = (
            f"⏳ <b>FLOOD_WAIT ALERT</b>\n\n"
            f"Telegram требует ждать <code>{retry_after}</code> секунд.{title_part}\n\n"
            f"Счётчик сегодня: {self._flood_wait_count}\n\n"
            f"<i>Проверь нагрузку на бота</i>"
        )
        return await self.send_alert(
            text, alert_type="flood_wait", cooldown_seconds=FLOOD_WAIT_ALERT_COOLDOWN_MINUTES * 60
        )

    def reset(self) -> None:
        """Сбросить все состояния алертов."""
        self._states.clear()
        self._flood_wait_count = 0
        self._last_flood_alert = 0.0


# Глобальный singleton
alert_manager = AlertManager()
