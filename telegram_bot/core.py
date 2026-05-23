"""
Модуль инициализации Telegram-бота.
- Использует HTML-разметку (ParseMode.HTML) для избежания ошибок Markdown.
- Импортирует config для токена и logging для логгера.
"""
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import config

logger = logging.getLogger(__name__)

bot = Bot(
    token=config.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)  # HTML, не Markdown!
)
dp = Dispatcher()