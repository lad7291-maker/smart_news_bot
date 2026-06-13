"""
Загрузчик и hot-reload для scoring.yaml.
P1-006: Внешняя конфигурация скоринга.

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

from models.scoring_config import ScoringConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: ScoringConfig = ScoringConfig(
    max_boost_total=10.0,
    source_score_range=(1, 10),
    source_scores={
        "Interfax": 5,
        "Security": 4,
        "RT": 5,
        "RIA": 5,
        "VC": 3,
        "Science": 2,
        "CoinTelegraph": 5,
        "CoinDesk": 5,
        "CNBC_World": 5,
        "NYT_Business": 5,
        "NYT_Economy": 5,
        "NYT_DealBook": 4,
        "Investing": 5,
        "NYT_Tech": 4,
    },
    boost_keywords={
        "трамп": 6.0,
        "путин": 6.0,
        "украина": 5.0,
        "война": 5.0,
        "санкции": 7.0,
        "атака": 4.0,
        "удар": 3.0,
        "теракт": 3.0,
        "обстрел": 1.0,
        "ракета": 4.0,
        "ядерный": 5.0,
        "мобилизация": 5.0,
        "иран": 5.0,
        "ставка": 6.0,
        "инфляция": 6.0,
        "дефолт": 6.0,
        "рецессия": 6.0,
        "кризис": 6.0,
        "нефть": 5.0,
        "газ": 5.0,
        "золото": 6.0,
        "Moex": 5.0,
        "биткоин": 5.0,
        "bitcoin": 5.0,
        "btc": 5.0,
        "выборы": 5.0,
        "импичмент": 5.0,
        "переговоры": 4.0,
        "саммит": 4.0,
        "резолюция": 4.0,
        "срочно": 3.0,
        "breaking": 1.0,
    },
    penalty_keywords=[
        "спорт",
        "футбол",
        "хоккей",
        "теннис",
        "олимпиада",
        "кино",
        "фильм",
        "актер",
        "режиссер",
        "музыка",
        "концерт",
        "шоу",
        "телевидение",
        "юмор",
        "знаменитость",
    ],
)


class ScoringConfigLoader:
    """Загружает scoring.yaml с валидацией и hot-reload."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = (
            Path(path) if path else Path(__file__).parent.parent / "config" / "scoring.yaml"
        )
        self._config: ScoringConfig = DEFAULT_CONFIG
        self._last_mtime: float = 0.0
        self._load()
        self._setup_sighup()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> ScoringConfig:
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
                f"scoring.yaml не найден по пути {self._path}. "
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
            logger.warning(f"scoring.yaml пуст. Fallback на дефолт.")
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        try:
            cfg = ScoringConfig(**raw)
        except Exception as exc:
            logger.warning(f"Ошибка валидации scoring.yaml: {exc}. Fallback на дефолт.")
            self._config = DEFAULT_CONFIG
            self._last_mtime = 0.0
            return False

        self._config = cfg
        self._last_mtime = os.path.getmtime(self._path)
        logger.info(
            f"scoring.yaml загружен: {len(cfg.source_scores)} источников, "
            f"{len(cfg.boost_keywords)} boost, {len(cfg.penalty_keywords)} penalty"
        )
        return True

    def _setup_sighup(self) -> None:
        """Регистрирует обработчик SIGHUP для hot-reload."""
        try:
            signal.signal(signal.SIGHUP, self._on_sighup)
            logger.debug("SIGHUP handler зарегистрирован для hot-reload scoring.yaml")
        except (ValueError, OSError):
            # Windows или другая платформа без SIGHUP
            pass

    def _on_sighup(self, signum: int, frame: Optional[object]) -> None:
        logger.info("Получен SIGHUP — перезагружаем scoring.yaml")
        self.reload()


# Глобальный singleton — используется всеми модулями
_scoring_loader: Optional[ScoringConfigLoader] = None


def get_scoring_loader(path: Optional[str] = None) -> ScoringConfigLoader:
    """Возвращает singleton ScoringConfigLoader."""
    global _scoring_loader
    if _scoring_loader is None:
        _scoring_loader = ScoringConfigLoader(path)
    return _scoring_loader


def get_scoring_config(path: Optional[str] = None) -> ScoringConfig:
    """Удобная обёртка — текущий конфиг скоринга."""
    return get_scoring_loader(path).config
