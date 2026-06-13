"""
Модуль скоринга новостей.
P1-001: Вынесен из bot_runner.py.
P1-006: Конфигурация вынесена во внешний scoring.yaml.

Оценивает новости по 10-балльной шкале на основе:
- Базового балла источника
- Ключевых слов (boost/penalty)
- Свежести
- Пользовательских предпочтений
- Реакций пользователей
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.scoring_config_loader import get_scoring_config
from storage.reactions import reactions_manager
from utils.logger import logger

# P1-006: SOURCE_SCORES, BOOST_KEYWORDS, PENALTY_KEYWORDS
# теперь загружаются из config/scoring.yaml через ScoringConfig.
# Для обратной совместимости используем _ScoringConfigProxy —
# прокси-объект, который поддерживает .items(), [], in, iter и т.д.


def _get_cfg():
    """Получает текущий (возможно, перезагруженный) конфиг скоринга."""
    return get_scoring_config()


class _ScoringConfigProxy:
    """Прокси-dict/list, который всегда читает актуальный конфиг."""

    def __init__(self, attr_name: str) -> None:
        self._attr = attr_name

    def _data(self):
        return getattr(_get_cfg(), self._attr)

    def items(self):
        return self._data().items()

    def keys(self):
        return self._data().keys()

    def values(self):
        return self._data().values()

    def get(self, key, default=None):
        return self._data().get(key, default)

    def __getitem__(self, key):
        return self._data()[key]

    def __contains__(self, key):
        return key in self._data()

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())

    def __repr__(self):
        return repr(self._data())


SOURCE_SCORES: Dict[str, float] = _ScoringConfigProxy("source_scores")  # type: ignore[assignment]
BOOST_KEYWORDS: Dict[str, float] = _ScoringConfigProxy("boost_keywords")  # type: ignore[assignment]
PENALTY_KEYWORDS: List[str] = _ScoringConfigProxy("penalty_keywords")  # type: ignore[assignment]


def detect_score(article: Dict[str, Any], user_prefs: Optional[Dict[str, Any]] = None) -> int:
    """
    Оценивает новость по 10-балльной шкале (1–10).

    Args:
        article: Словарь с данными новости
        user_prefs: Персональные предпочтения пользователя

    Returns:
        int: Оценка от 1 до 10
    """
    cfg = _get_cfg()
    source_tag = (article.get("source_tag") or article.get("source") or "").strip()
    base_score = cfg.get_source_score(source_tag, default=2.0)

    # Персонализированный вес источника
    if user_prefs:
        source_weights = user_prefs.get("source_weights", {})
        if source_tag in source_weights:
            weight = source_weights[source_tag]
            base_score = max(1, min(10, int(round(base_score * weight))))

    # Бонус за ключевые слова (максимум из найденных)
    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()
    text = f"{title} {summary}"
    boost = cfg.get_max_boost(text)

    # Бонус за предпочитаемые темы
    if user_prefs:
        preferred = user_prefs.get("preferred_topics", [])
        for topic in preferred:
            if topic.lower() in text:
                boost = max(boost, 2.0)
                break

    # Штраф за нерелевантные темы
    penalty = 0.0
    if cfg.has_penalty_keyword(text):
        penalty = -1.0

    # Штраф за заблокированные темы
    if user_prefs:
        blocked = user_prefs.get("blocked_topics", [])
        for topic in blocked:
            if topic.lower() in text:
                penalty = -5.0
                break

    # Бонус за свежесть
    freshness = 0.0
    published = article.get("published")
    if published:
        age = datetime.now() - published
        hours = age.total_seconds() / 3600
        if hours < 6:
            freshness = 0.5
        elif hours < 12:
            freshness = 0.3
        elif hours < 24:
            freshness = 0.1

    total = base_score + boost + penalty + freshness

    # Учитываем реакции пользователей
    article_link = article.get("link", "")
    if article_link:
        reaction_boost = reactions_manager.get_article_score_boost(article_link)
        total += reaction_boost

    return max(1, min(10, int(round(total))))


def get_delay_for_score(score: int, mode: str, quiet: bool) -> int:
    """Возвращает задержку напрямую по баллу."""
    if score >= 8:
        return 0  # red
    elif score >= 5:
        return 0  # orange
    else:
        return 1800  # yellow: 30 мин fallback
