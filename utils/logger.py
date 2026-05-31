import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config import config

def setup_logging():
    """Настройка продвинутого логирования с UTF-8 и ротацией (FEAT-010)"""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    # Очищаем старые обработчики
    logger.handlers.clear()
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter(
        '%(levelname)-8s | %(message)s'
    )
    
    # Файловый лог с ротацией (FEAT-010): 10 МБ, храним 5 бэкапов
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        encoding='utf-8',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Файл ошибок с ротацией (FEAT-010)
    error_handler = RotatingFileHandler(
        logs_dir / "errors.log",
        encoding='utf-8',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Консольный лог
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(error_handler)
    
    return logger

# Пытаемся настроить логгер при импорте.
# Если config ещё не готов (редко), создаём fallback.
try:
    _logger = setup_logging()
except Exception:
    _logger = logging.getLogger()
    _logger.setLevel(logging.INFO)
    _logger.addHandler(logging.StreamHandler())

# Экспортируем как logger для обратной совместимости
logger = _logger