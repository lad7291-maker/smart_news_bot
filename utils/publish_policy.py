"""
Политика публикаций для Smart News Bot.
Реализует трёхуровневую систему скорости, тихие часы,
rate limiting, антиспам по темам и адаптивные задержки.
"""
import random
import pytz
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from utils.logger import logger

# === НАСТРОЙКИ ===
MSK = pytz.timezone("Europe/Moscow")

# Тихие часы: 23:00 - 07:00 МСК
QUIET_HOURS_START = 23
QUIET_HOURS_END = 7

# Rate limits
MAX_POSTS_PER_HOUR = 8
STORM_RED_THRESHOLD = 3  # сколько 🔴 за час включает режим шторма

# Задержки (секунды)
DELAY_RED = 0
DELAY_ORANGE_QUIET = 300       # 5 мин
DELAY_ORANGE_NORMAL_MIN = 900  # 15 мин
DELAY_ORANGE_NORMAL_MAX = 1800 # 30 мин
DELAY_YELLOW_MIN = 7200        # 2 часа
DELAY_YELLOW_MAX = 14400       # 4 часа

# Кулдаун по темам (секунды)
TOPIC_COOLDOWN_MIN = 2400      # 40 мин
TOPIC_COOLDOWN_MAX = 3600      # 60 мин

# Ключевые слова для кулдауна (персоны и горячие темы)
TOPIC_KEYWORDS = [
    "трамп", "trump",
    "путин", "putin",
    "байден", "biden",
    "украина", "ukraine",
    "иран", "iran",
    "израиль", "israel",
    "нато", "nato",
    "китай", "china",
    "евросоюз", "european union", "ec",
]

# История публикаций в памяти (score, level, title, source, timestamp)
_recent_publishes: list[Dict[str, Any]] = []


def _cleanup_old_records():
    """Удаляет записи старше 2 часов."""
    cutoff = datetime.now() - timedelta(hours=2)
    global _recent_publishes
    _recent_publishes = [r for r in _recent_publishes if r["ts"] > cutoff]


def record_publish(score: int, title: str, source: str):
    """Записывает факт публикации для статистики."""
    _recent_publishes.append({
        "score": score,
        "level": get_publish_level(score),
        "title": title,
        "source": source,
        "ts": datetime.now(),
    })
    _cleanup_old_records()


def get_publish_level(score: int) -> str:
    """
    Определяет уровень публикации по баллу.
    red (9-10), orange (7-8), yellow (1-6).
    """
    if score >= 9:
        return "red"
    elif score >= 7:
        return "orange"
    else:
        return "yellow"


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
    """Проверяет, находимся ли сейчас в тихих часах (23:00-07:00 МСК)."""
    if now is None:
        now = datetime.now(MSK)
    hour = now.hour
    return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END


def get_recent_stats(hours: float = 1.0) -> dict:
    """
    Возвращает статистику публикаций за последние N часов.
    """
    _cleanup_old_records()
    since = datetime.now() - timedelta(hours=hours)
    recent = [r for r in _recent_publishes if r["ts"] > since]

    stats = {
        "total": len(recent),
        "red": sum(1 for r in recent if r["level"] == "red"),
        "orange": sum(1 for r in recent if r["level"] == "orange"),
        "yellow": sum(1 for r in recent if r["level"] == "yellow"),
    }
    return stats


def get_mode() -> str:
    """
    Определяет режим ленты по публикациям за последний час:
    - STORM: 3+ red за час
    - QUIET: 0 red и <=1 orange за час
    - NORMAL: всё остальное
    """
    stats = get_recent_stats(hours=1.0)
    if stats["red"] >= STORM_RED_THRESHOLD:
        return "storm"
    if stats["red"] == 0 and stats["orange"] <= 1:
        return "quiet"
    return "normal"


def should_publish(
    level: str,
    score: int,
    mode: str,
    quiet: bool,
) -> Tuple[bool, str]:
    """
    Решает, можно ли публиковать новость прямо сейчас.
    Возвращает (allowed, reason).
    """
    stats = get_recent_stats(hours=1.0)

    # 🔴 Экстренный
    if level == "red":
        if quiet:
            # RED 10 - всегда, RED 9 - откладываем до утра
            if score >= 10:
                return True, "red_immediate_night"
            return False, "red_high_deferred_to_morning"
        return True, "red_immediate"

    # 🟠 Важный
    if level == "orange":
        if quiet:
            return False, "orange_quiet_hours"
        # В шторм orange тоже публикуем, но с задержкой
        if mode == "storm":
            return True, "orange_storm_delayed"
        # Проверка глобального rate limit
        if stats["total"] >= MAX_POSTS_PER_HOUR:
            return False, "orange_rate_limit"
        return True, "orange_ok"

    # 🟡 Обычный
    if level == "yellow":
        # В шторм yellow тоже публикуем с большой задержкой
        if mode == "storm":
            return True, "yellow_storm_delayed"
        # В обычном режиме — с задержкой 2-4 часа
        return True, "yellow_delayed"

    return False, "unknown_level"


def get_delay_seconds(
    level: str,
    score: int,
    mode: str,
    quiet: bool,
) -> Optional[int]:
    """
    Возвращает задержку в секундах для планирования публикации.
    None означает "не планировать в ленту, уйти в дайджест/отложенные".
    """
    if level == "red":
        if quiet and score < 10:
            # Откладываем до 07:00 утра МСК
            now = datetime.now(MSK)
            if now.hour >= QUIET_HOURS_START:
                next_morning = now.replace(hour=QUIET_HOURS_END, minute=0, second=0, microsecond=0) + timedelta(days=1)
            else:
                next_morning = now.replace(hour=QUIET_HOURS_END, minute=0, second=0, microsecond=0)
            delay = int((next_morning - now).total_seconds())
            return max(delay, 300)
        return DELAY_RED

    if level == "orange":
        if mode == "storm":
            # В шторм публикуем с небольшой задержкой (3-7 мин)
            return random.randint(180, 420)
        if mode == "quiet":
            return DELAY_ORANGE_QUIET
        # NORMAL: рандом 15-30 мин
        return random.randint(DELAY_ORANGE_NORMAL_MIN, DELAY_ORANGE_NORMAL_MAX)

    if level == "yellow":
        if mode == "storm":
            # В шторм yellow публикуем с небольшой задержкой (3-7 мин)
            return random.randint(180, 420)
        # В обычном режиме — большая задержка (2-4 часа)
        return random.randint(DELAY_YELLOW_MIN, DELAY_YELLOW_MAX)

    return None


def check_topic_cooldown(title: str, level: str) -> Tuple[bool, str, int]:
    """
    Проверяет кулдаун по темам/персонам.
    🔴 игнорирует кулдаун.
    Возвращает (allowed, reason, cooldown_remaining_seconds).
    """
    if level == "red":
        return True, "red_no_cooldown", 0

    title_lower = title.lower()
    now = datetime.now()
    cooldown_window = timedelta(seconds=random.randint(TOPIC_COOLDOWN_MIN, TOPIC_COOLDOWN_MAX))
    since = now - cooldown_window

    _cleanup_old_records()
    recent = [r for r in _recent_publishes if r["ts"] > since]

    for keyword in TOPIC_KEYWORDS:
        if keyword in title_lower:
            for rec in recent:
                if keyword in rec["title"].lower():
                    remaining = int((rec["ts"] + cooldown_window - now).total_seconds())
                    if remaining > 0:
                        logger.info(
                            f"⏳ Кулдаун по теме '{keyword}': {remaining//60} мин"
                        )
                        return False, f"topic_cooldown_{keyword}", remaining

    return True, "no_cooldown", 0
