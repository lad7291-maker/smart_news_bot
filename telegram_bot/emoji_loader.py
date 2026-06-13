"""
Загрузчик и hot-reload для emojis.yaml.
P2-001: Рефакторинг _detect_topic_emoji().

Поддерживает:
- Загрузку при старте с fallback на дефолтные значения
- Hot-reload по сигналу SIGHUP
- Периодическую проверку изменений (mtime)
- Валидацию через Pydantic
"""

import logging
import os
import signal
from pathlib import Path
from typing import Optional

import yaml

from models.emoji_config import EmojiConfig, EmojiRule

logger = logging.getLogger(__name__)

# Дефолтные правила (inline fallback)
DEFAULT_CONFIG = EmojiConfig(
    rules=[
        EmojiRule(emoji="🇷🇺", keywords=["россия", "рф", "москва", "путин", "кремль", "российск"]),
        EmojiRule(
            emoji="🇺🇸",
            keywords=[
                "сша",
                "америка",
                "байден",
                "трамп",
                "вашингтон",
                "белый дом",
                "biden",
                "trump",
            ],
        ),
        EmojiRule(emoji="🇨🇳", keywords=["китай", "пекин", "china", "beijing"]),
        EmojiRule(emoji="🇺🇦", keywords=["украина", "киев", "зеленский", "ukraine", "kyiv"]),
        EmojiRule(
            emoji="🇪🇺",
            keywords=[
                "евросоюз",
                "европа",
                "европейск",
                "брюссель",
                "ecb",
                "european union",
                "eu ",
            ],
        ),
        EmojiRule(
            emoji="⚔️",
            keywords=[
                "война",
                "конфликт",
                "атака",
                "удар",
                "ракет",
                "дрон",
                "war",
                "conflict",
                "attack",
            ],
        ),
        EmojiRule(
            emoji="💰",
            keywords=["инфляц", "кризис", "эконом", "рецессия", "inflation", "crisis", "economy"],
        ),
        EmojiRule(
            emoji="🏦",
            keywords=["цб", "центробанк", "central bank", "federal reserve", "fed ", "ecb"],
        ),
        EmojiRule(
            emoji="₿", keywords=["биткоин", "bitcoin", "btc", "криптовалют", "crypto", "blockchain"]
        ),
        EmojiRule(emoji="🛢️", keywords=["нефт", "газ", "oil", "gas", "energy", "opec"]),
        EmojiRule(emoji="🏅", keywords=["золот", "золото", "gold", "silver", "commodity"]),
        EmojiRule(
            emoji="🤖",
            keywords=[
                "искусственный интеллект",
                "нейросет",
                "ai ",
                "artificial intelligence",
                "tech",
                "technology",
            ],
        ),
        EmojiRule(emoji="🔒", keywords=["кибер", "хакер", "cyber", "hacker", "hack", "breach"]),
        EmojiRule(emoji="📈", keywords=["бирж", "акци", "stock", "ipo", "merger", "moex"]),
        EmojiRule(emoji="🏠", keywords=["недвижим", "real estate", "housing", "mortgage"]),
        EmojiRule(emoji="🚫", keywords=["санкц", "sanction", "тариф", "tariff", "embargo"]),
        EmojiRule(emoji="🗳️", keywords=["выборы", "election", "vote", "парламент", "parliament"]),
        EmojiRule(
            emoji="🌊", keywords=["землетрясен", "earthquake", "flood", "hurricane", "climate"]
        ),
        EmojiRule(
            emoji="🏥", keywords=["ковид", "пандем", "covid", "pandemic", "vaccine", "virus"]
        ),
        EmojiRule(
            emoji="🚀", keywords=["космос", "space", "rocket", "satellite", "nasa", "spacex"]
        ),
        EmojiRule(emoji="🚗", keywords=["авто", "car ", "auto ", "vehicle", "aviation", "tesla"]),
        EmojiRule(
            emoji="🌾", keywords=["сельскохозяйственн", "agriculture", "farm", "wheat", "crop"]
        ),
    ],
    source_emoji={
        "VC": "💻",
        "Science": "🔬",
        "Security": "🔒",
        "Interfax": "📰",
        "RT": "📰",
        "RIA": "📰",
        "CoinDesk": "₿",
        "Investing": "📊",
        "CoinTelegraph": "₿",
        "CNBC_World": "📰",
        "NYT_Business": "📰",
        "NYT_Economy": "📰",
        "NYT_Tech": "💻",
        "NYT_DealBook": "🤝",
    },
    default_emoji="📰",
)


class EmojiConfigLoader:
    """Загружает emojis.yaml с валидацией и hot-reload."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = Path(path) if path else Path(__file__).parent.parent / "config" / "emojis.yaml"
        self._config: EmojiConfig = DEFAULT_CONFIG
        self._last_mtime: float = 0.0
        self._load()
        self._setup_sighup()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> EmojiConfig:
        """Текущий (возможно, перезагруженный) конфиг."""
        return self._config

    def reload(self) -> bool:
        """Принудительная перезагрузка. Возвращает True при успехе."""
        return self._load()

    def check_and_reload(self) -> bool:
        """Перезагрузить, если файл изменился с последней загрузки."""
        if not self._path.exists():
            return False
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            return False
        if mtime > self._last_mtime:
            return self._load()
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> bool:
        if not self._path.exists():
            logger.warning(
                f"emojis.yaml не найден по пути {self._path}. "
                f"Используется конфигурация по умолчанию."
            )
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logger.warning(f"Невалидный YAML в {self._path}: {exc}. Fallback на дефолт.")
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        if raw is None:
            logger.warning(f"emojis.yaml пуст. Fallback на дефолт.")
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        try:
            cfg = EmojiConfig(**raw)
        except Exception as exc:
            logger.warning(f"Ошибка валидации emojis.yaml: {exc}. Fallback на дефолт.")
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        self._config = cfg
        self._last_mtime = os.path.getmtime(self._path)
        logger.info(
            f"emojis.yaml загружен: {len(cfg.rules)} правил, "
            f"{len(cfg.source_emoji)} source_emoji"
        )
        return True

    def _setup_sighup(self) -> None:
        try:
            signal.signal(signal.SIGHUP, self._on_sighup)
            logger.debug("SIGHUP handler зарегистрирован для hot-reload emojis.yaml")
        except (ValueError, OSError):
            pass

    def _on_sighup(self, signum: int, frame: Optional[object]) -> None:
        logger.info("Получен SIGHUP — перезагружаем emojis.yaml")
        self.reload()


# Глобальный singleton
_emoji_loader: Optional[EmojiConfigLoader] = None


def get_emoji_loader(path: Optional[str] = None) -> EmojiConfigLoader:
    """Возвращает singleton EmojiConfigLoader."""
    global _emoji_loader
    if _emoji_loader is None:
        _emoji_loader = EmojiConfigLoader(path)
    return _emoji_loader


def get_emoji_config(path: Optional[str] = None) -> EmojiConfig:
    """Удобная обёртка — текущий конфиг эмодзи."""
    return get_emoji_loader(path).config
