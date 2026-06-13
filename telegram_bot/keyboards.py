"""
Inline-клавиатуры для Telegram-бота.
P1-001: Вынесены из bot_runner.py.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from storage.cache import cache_manager

# === FEAT-019: Предустановленные темы ===
_PRESET_TOPICS = [
    ("₿ Крипто", "крипто"),
    ("🏛 Политика", "политика"),
    ("💰 Экономика", "экономика"),
    ("⚔️ Война", "война"),
    ("🤖 Технологии", "технологии"),
    ("🏦 Центробанки", "центробанк"),
    ("🛢️ Нефть/Газ", "нефть"),
    ("🚀 Космос", "космос"),
]

_PRESET_BLOCKED = [
    ("🏀 Спорт", "спорт"),
    ("🎬 Кино", "кино"),
    ("🎵 Музыка", "музыка"),
]


def build_start_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура для /start (FEAT-005)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 Собрать новости", callback_data="post_now")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="🏆 Топ новостей", callback_data="top")],
            [InlineKeyboardButton(text="📈 Аналитика", callback_data="analytics")],
            [InlineKeyboardButton(text="🧪 A/B результаты", callback_data="ab_results")],
            [InlineKeyboardButton(text="🏅 A/B winner", callback_data="ab_winner")],
            [InlineKeyboardButton(text="📉 Метрики", callback_data="metrics")],
            [InlineKeyboardButton(text="🤖 AI стоимость", callback_data="ai_cost")],
            [InlineKeyboardButton(text="⚙️ Мои настройки", callback_data="settings_menu")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        ]
    )


def build_settings_keyboard(chat_id: str) -> InlineKeyboardMarkup:
    """Главное меню настроек (FEAT-019)."""
    prefs = cache_manager.get_user_prefs(chat_id)
    preferred = set(prefs.get("preferred_topics", []))
    blocked = set(prefs.get("blocked_topics", []))
    min_score = prefs.get("min_score", 1)

    kb = []
    kb.append([InlineKeyboardButton(text="✅ Подписаться на тему ▼", callback_data="noop")])

    # Темы для подписки (по 2 в ряд)
    topic_rows = []
    for label, topic in _PRESET_TOPICS:
        icon = "✅" if topic in preferred else "⬜"
        topic_rows.append(
            InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"topic_toggle:{topic}")
        )
        if len(topic_rows) == 2:
            kb.append(topic_rows)
            topic_rows = []
    if topic_rows:
        kb.append(topic_rows)

    kb.append([InlineKeyboardButton(text="🚫 Заблокировать тему ▼", callback_data="noop")])

    block_rows = []
    for label, topic in _PRESET_BLOCKED:
        icon = "🚫" if topic in blocked else "⬜"
        block_rows.append(
            InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"block_toggle:{topic}")
        )
        if len(block_rows) == 2:
            kb.append(block_rows)
            block_rows = []
    if block_rows:
        kb.append(block_rows)

    kb.append(
        [
            InlineKeyboardButton(
                text=f"📊 Минимальный балл: {min_score}", callback_data="minscore_menu"
            )
        ]
    )
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def build_minscore_keyboard(current: int) -> InlineKeyboardMarkup:
    """Меню выбора минимального балла."""
    kb = []
    row = []
    for score in range(1, 11):
        icon = "●" if score == current else "○"
        row.append(
            InlineKeyboardButton(text=f"{icon} {score}", callback_data=f"minscore_set:{score}")
        )
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
