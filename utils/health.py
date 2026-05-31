"""
Модуль health-check для Smart News Bot.
Проверяет жизнеспособность бота и отправляет алерты админу.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.logger import logger

# ID администратора для алертов
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# Флаг: отправлять ли алерт (чтобы не спамить)
_alert_sent = False
_last_alert_time: Optional[datetime] = None
_ALERT_COOLDOWN_MINUTES = 30  # не чаще 1 алерта в 30 мин

# Пороги для алертов
MAX_SILENCE_MINUTES = 30  # Максимальное время молчания
MAX_ERROR_RATE = 10  # Максимальное количество ошибок за час


class HealthChecker:
    """Проверяет состояние бота и отправляет алерты."""

    def __init__(self, bot=None, admin_id: int = ADMIN_ID):
        self.bot = bot
        self.admin_id = admin_id
        self.last_publish_time: Optional[datetime] = None
        self.error_count = 0
        self.last_error_reset = datetime.now()

    def record_publish(self):
        """Записывает факт публикации."""
        self.last_publish_time = datetime.now()

    def record_error(self):
        """Записывает факт ошибки."""
        now = datetime.now()
        if now - self.last_error_reset > timedelta(hours=1):
            self.error_count = 0
            self.last_error_reset = now
        self.error_count += 1

    def get_status(self) -> Dict[str, Any]:
        """Возвращает текущий статус бота."""
        now = datetime.now()
        status = {
            "healthy": True,
            "last_publish": self.last_publish_time.isoformat() if self.last_publish_time else None,
            "errors_last_hour": self.error_count,
            "checks": {},
        }

        # Проверка: давно ли была публикация
        if self.last_publish_time:
            silence_minutes = (now - self.last_publish_time).total_seconds() / 60
            status["checks"]["silence"] = {
                "minutes": round(silence_minutes, 1),
                "threshold": MAX_SILENCE_MINUTES,
                "ok": silence_minutes < MAX_SILENCE_MINUTES,
            }
            if not status["checks"]["silence"]["ok"]:
                status["healthy"] = False
        else:
            status["checks"]["silence"] = {"ok": True, "note": "No publishes yet"}

        # Проверка: количество ошибок
        status["checks"]["errors"] = {
            "count": self.error_count,
            "threshold": MAX_ERROR_RATE,
            "ok": self.error_count < MAX_ERROR_RATE,
        }
        if not status["checks"]["errors"]["ok"]:
            status["healthy"] = False

        return status

    async def check_and_alert(self):
        """Проверяет состояние и отправляет алерт админу при проблемах."""
        global _alert_sent, _last_alert_time

        status = self.get_status()

        if status["healthy"]:
            # Сбрасываем флаг алерта при восстановлении
            if _alert_sent:
                _alert_sent = False
                logger.info("✅ Health check recovered")
                if self.bot and self.admin_id:
                    try:
                        await self.bot.send_message(
                            chat_id=self.admin_id,
                            text="✅ <b>Bot Health Recovered</b>\n\nБот снова работает нормально.",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send recovery alert: {e}")
            return

        # Проверяем cooldown (не спамим алертами)
        now = datetime.now()
        if (
            _last_alert_time
            and (now - _last_alert_time).total_seconds() < _ALERT_COOLDOWN_MINUTES * 60
        ):
            logger.debug(f"Health alert cooldown ({_ALERT_COOLDOWN_MINUTES} min)")
            return

        # Формируем сообщение об ошибке
        issues = []
        for check_name, check_data in status["checks"].items():
            if not check_data.get("ok", True):
                if check_name == "silence":
                    issues.append(
                        f"🔇 Молчание {check_data['minutes']:.0f} мин (порог {check_data['threshold']})"
                    )
                elif check_name == "errors":
                    issues.append(
                        f"❌ Ошибок: {check_data['count']} за час (порог {check_data['threshold']})"
                    )

        message = (
            f"🚨 <b>ALERT: Bot Health Check Failed</b>\n\n"
            + "\n".join(f"• {issue}" for issue in issues)
            + "\n\n<i>Следующий алерт не раньше чем через 30 мин.</i>"
        )
        logger.warning(f"Health check failed: {issues}")

        # Отправляем админу
        if self.bot and self.admin_id:
            try:
                await self.bot.send_message(chat_id=self.admin_id, text=message, parse_mode="HTML")
                _alert_sent = True
                _last_alert_time = now
            except Exception as e:
                logger.error(f"Failed to send health alert: {e}")
        else:
            logger.warning(
                f"Cannot send alert: bot={self.bot is not None}, admin_id={self.admin_id}"
            )


# Глобальный экземпляр
health_checker = HealthChecker()


async def periodic_health_check(bot=None, interval_minutes: int = 15):
    """Запускает периодическую проверку здоровья бота."""
    if bot:
        health_checker.bot = bot

    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            await health_checker.check_and_alert()
        except Exception as e:
            logger.error(f"Health check error: {e}")
