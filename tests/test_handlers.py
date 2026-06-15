"""
Тесты для telegram_bot/handlers.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

# Патчим _deps перед импортом модулей
from telegram_bot import handlers

# ─── Helpers ───────────────────────────────────────────────────────────────


def _make_message(text="/start", user_id=42, chat_id=100) -> Message:
    """Создаёт фейковое Message для тестов."""
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=User)
    msg.from_user.id = user_id
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    return msg


def _make_callback(data="post_now", user_id=42, chat_id=100) -> CallbackQuery:
    """Создаёт фейковый CallbackQuery для тестов."""
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock(spec=User)
    cb.from_user.id = user_id
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = chat_id
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_deps():
    """Сбрасывает _deps перед каждым тестом."""
    handlers._deps.clear()
    yield
    handlers._deps.clear()


@pytest.fixture
def admin_deps():
    """Заполняет _deps с ADMIN_ID=42 и моками зависимостей."""
    mock_config = MagicMock()
    mock_config.PUBLISH_INTERVAL_MINUTES = 15

    mock_cache = MagicMock()
    mock_cache.get_processing_stats.return_value = {"total": 100, "processed": 80, "failed": 5}
    mock_cache.get_user_prefs.return_value = {
        "preferred_topics": [],
        "blocked_topics": [],
        "min_score": 1,
    }

    mock_scheduler = MagicMock()
    mock_scheduler.get_jobs.return_value = []

    mock_reactions = MagicMock()
    mock_reactions.get_top_articles.return_value = []

    mock_analytics = MagicMock()
    mock_analytics.get_analytics_report.return_value = {
        "delivery_24h": {
            "total_sent": 10,
            "delivered": 9,
            "delivery_rate": 90.0,
            "with_image": 5,
            "fallback_images": 1,
        },
        "delivery_7d": {"total_sent": 50, "delivered": 48, "delivery_rate": 96.0},
        "errors_24h": {"total_errors": 0, "flood_wait": 0, "api_errors": 0, "network_errors": 0},
        "errors_7d": {"total_errors": 2, "flood_wait": 0, "api_errors": 1, "network_errors": 1},
        "top_sources": [],
        "dau": 1,
        "mau": 1,
    }
    mock_analytics.get_ai_cost.return_value = {
        "requests": 10,
        "tokens_input": 1000,
        "tokens_output": 500,
        "cost_usd": 0.05,
    }
    mock_analytics.get_ai_cost_by_provider.return_value = []
    mock_analytics.check_ai_cost_alert.return_value = (False, 0.0)
    mock_analytics.record_user_session = MagicMock()

    mock_ab = MagicMock()
    mock_ab.get_report_text.return_value = "<b>A/B Report</b>"
    mock_ab.get_winner_status_text.return_value = "Winner: control"
    mock_ab.reset_winner.return_value = True

    mock_health = AsyncMock()
    mock_health.get_full_status = AsyncMock(
        return_value={
            "healthy": True,
            "last_publish": "2024-01-01T00:00:00",
            "errors_last_hour": 0,
            "checks": {
                "silence": {"ok": True, "minutes": 5, "threshold": 30},
                "errors": {"ok": True, "count": 0, "threshold": 10},
            },
            "api_checks": {},
        }
    )

    mock_source_tracker = MagicMock()
    mock_source_tracker.get_all_statuses.return_value = []

    deps = {
        "ADMIN_ID": 42,
        "config": mock_config,
        "SCORE_DELAYS": {"high": 0, "medium": 30, "low": 120},
        "cache_manager": mock_cache,
        "scheduler": mock_scheduler,
        "reactions_manager": mock_reactions,
        "analytics_manager": mock_analytics,
        "ab_testing_manager": mock_ab,
        "health_checker": mock_health,
        "source_tracker": mock_source_tracker,
        "job_collect_news": AsyncMock(),
    }
    handlers._deps.update(deps)
    return deps


# ─── Admin access tests ────────────────────────────────────────────────────


class TestAdminAccess:
    """Тесты проверки доступа администратора."""

    def test_is_admin_true(self):
        handlers._deps["ADMIN_ID"] = 42
        assert handlers._is_admin(42) is True

    def test_is_admin_false(self):
        handlers._deps["ADMIN_ID"] = 42
        assert handlers._is_admin(99) is False

    @pytest.mark.asyncio
    async def test_require_admin_blocks_non_admin(self):
        handlers._deps["ADMIN_ID"] = 42
        msg = _make_message(user_id=99)
        result = await handlers._require_admin(msg)
        assert result is False
        msg.answer.assert_called_once()
        assert "Доступ запрещён" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        handlers._deps["ADMIN_ID"] = 42
        msg = _make_message(user_id=42)
        result = await handlers._require_admin(msg)
        assert result is True
        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_require_admin_callback_blocks_non_admin(self):
        handlers._deps["ADMIN_ID"] = 42
        cb = _make_callback(user_id=99)
        result = await handlers._require_admin_callback(cb)
        assert result is False
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_require_admin_callback_allows_admin(self):
        handlers._deps["ADMIN_ID"] = 42
        cb = _make_callback(user_id=42)
        result = await handlers._require_admin_callback(cb)
        assert result is True
        cb.answer.assert_not_called()


# ─── Message handlers ──────────────────────────────────────────────────────


class TestCmdStart:
    """Тесты /start."""

    @pytest.mark.asyncio
    async def test_start_sends_keyboard(self, admin_deps):
        msg = _make_message("/start", user_id=42)
        await handlers.cmd_start(msg)
        msg.answer.assert_called_once()
        args = msg.answer.call_args
        assert "Smart News Bot" in args[0][0]
        assert args[1].get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_start_blocks_non_admin(self):
        handlers._deps["ADMIN_ID"] = 42
        msg = _make_message("/start", user_id=99)
        await handlers.cmd_start(msg)
        # Первый вызов — отказ в доступе
        assert msg.answer.call_count == 1
        assert "Доступ запрещён" in msg.answer.call_args[0][0]


class TestCmdPostNow:
    """Тесты /post_now."""

    @pytest.mark.asyncio
    async def test_post_now_launches_job(self, admin_deps):
        msg = _make_message("/post_now", user_id=42)
        await handlers.cmd_post_now(msg)
        assert msg.answer.call_count == 2
        assert "Запускаю" in msg.answer.call_args_list[0][0][0]
        assert "Задача запущена" in msg.answer.call_args_list[1][0][0]
        admin_deps["job_collect_news"].assert_called_once()


class TestCmdStats:
    """Тесты /stats."""

    @pytest.mark.asyncio
    async def test_stats_returns_data(self, admin_deps):
        msg = _make_message("/stats", user_id=42)
        await handlers.cmd_stats(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Статистика" in text
        assert "100" in text  # total from mock


class TestCmdTop:
    """Тесты /top."""

    @pytest.mark.asyncio
    async def test_top_empty(self, admin_deps):
        msg = _make_message("/top", user_id=42)
        await handlers.cmd_top(msg)
        msg.answer.assert_called_once()
        assert "нет реакций" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_top_with_articles(self, admin_deps):
        admin_deps["reactions_manager"].get_top_articles.return_value = [
            {
                "article_title": "Test News",
                "likes": 5,
                "dislikes": 1,
                "saves": 2,
                "source_tag": "Test",
                "score": 8,
            }
        ]
        msg = _make_message("/top", user_id=42)
        await handlers.cmd_top(msg)
        text = msg.answer.call_args[0][0]
        assert "Test News" in text
        assert "5" in text


class TestCmdAnalytics:
    """Тесты /analytics."""

    @pytest.mark.asyncio
    async def test_analytics_returns_report(self, admin_deps):
        msg = _make_message("/analytics", user_id=42)
        await handlers.cmd_analytics(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Аналитика" in text
        assert "DAU" in text


class TestCmdABResults:
    """Тесты /ab_results."""

    @pytest.mark.asyncio
    async def test_ab_results_returns_html(self, admin_deps):
        msg = _make_message("/ab_results", user_id=42)
        await handlers.cmd_ab_results(msg)
        msg.answer.assert_called_once()
        assert msg.answer.call_args[1].get("parse_mode") == "HTML"


class TestCmdABWinner:
    """Тесты /ab_winner."""

    @pytest.mark.asyncio
    async def test_ab_winner_status(self, admin_deps):
        msg = _make_message("/ab_winner", user_id=42)
        await handlers.cmd_ab_winner(msg)
        msg.answer.assert_called_once()
        assert "Winner" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_ab_winner_reset(self, admin_deps):
        msg = _make_message("/ab_winner reset", user_id=42)
        await handlers.cmd_ab_winner(msg)
        msg.answer.assert_called_once()
        admin_deps["ab_testing_manager"].reset_winner.assert_called_once()


class TestCmdMetrics:
    """Тесты /metrics."""

    @pytest.mark.asyncio
    async def test_metrics_returns_html(self, admin_deps):
        with patch("utils.metrics.collector") as mock_collector:
            mock_collector.get_report_text.return_value = "<b>Metrics</b>"
            msg = _make_message("/metrics", user_id=42)
            await handlers.cmd_metrics(msg)
            msg.answer.assert_called_once()
            assert msg.answer.call_args[1].get("parse_mode") == "HTML"


class TestCmdAICost:
    """Тесты /ai_cost."""

    @pytest.mark.asyncio
    async def test_ai_cost_returns_report(self, admin_deps):
        msg = _make_message("/ai_cost", user_id=42)
        await handlers.cmd_ai_cost(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Стоимость AI" in text


class TestCmdHelp:
    """Тесты /help."""

    @pytest.mark.asyncio
    async def test_help_calls_start(self, admin_deps):
        msg = _make_message("/help", user_id=42)
        await handlers.cmd_help(msg)
        msg.answer.assert_called_once()
        assert "Smart News Bot" in msg.answer.call_args[0][0]


# ─── Personalization commands ──────────────────────────────────────────────


class TestCmdTopic:
    """Тесты /topic."""

    @pytest.mark.asyncio
    async def test_topic_no_args(self, admin_deps):
        msg = _make_message("/topic", user_id=42)
        await handlers.cmd_topic(msg)
        msg.answer.assert_called_once()
        assert "Укажи тему" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_topic_subscribe(self, admin_deps):
        msg = _make_message("/topic крипто", user_id=42)
        await handlers.cmd_topic(msg)
        msg.answer.assert_called_once()
        assert "Подписка" in msg.answer.call_args[0][0]
        admin_deps["cache_manager"].set_user_prefs.assert_called()

    @pytest.mark.asyncio
    async def test_topic_already_subscribed(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": ["крипто"],
            "blocked_topics": [],
            "min_score": 1,
        }
        msg = _make_message("/topic крипто", user_id=42)
        await handlers.cmd_topic(msg)
        assert "уже подписан" in msg.answer.call_args[0][0]


class TestCmdNotopic:
    """Тесты /notopic."""

    @pytest.mark.asyncio
    async def test_notopic_unsubscribe(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": ["крипто"],
            "blocked_topics": [],
            "min_score": 1,
        }
        msg = _make_message("/notopic крипто", user_id=42)
        await handlers.cmd_notopic(msg)
        assert "отменена" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_notopic_not_subscribed(self, admin_deps):
        msg = _make_message("/notopic крипто", user_id=42)
        await handlers.cmd_notopic(msg)
        assert "не подписан" in msg.answer.call_args[0][0]


class TestCmdBlock:
    """Тесты /block."""

    @pytest.mark.asyncio
    async def test_block_topic(self, admin_deps):
        msg = _make_message("/block спорт", user_id=42)
        await handlers.cmd_block(msg)
        assert "заблокирована" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_block_already_blocked(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": [],
            "blocked_topics": ["спорт"],
            "min_score": 1,
        }
        msg = _make_message("/block спорт", user_id=42)
        await handlers.cmd_block(msg)
        assert "уже заблокирована" in msg.answer.call_args[0][0]


class TestCmdUnblock:
    """Тесты /unblock."""

    @pytest.mark.asyncio
    async def test_unblock_topic(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": [],
            "blocked_topics": ["спорт"],
            "min_score": 1,
        }
        msg = _make_message("/unblock спорт", user_id=42)
        await handlers.cmd_unblock(msg)
        assert "разблокирована" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unblock_not_blocked(self, admin_deps):
        msg = _make_message("/unblock спорт", user_id=42)
        await handlers.cmd_unblock(msg)
        assert "не заблокирована" in msg.answer.call_args[0][0]


class TestCmdMytopics:
    """Тесты /mytopics."""

    @pytest.mark.asyncio
    async def test_mytopics_shows_prefs(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": ["крипто"],
            "blocked_topics": ["спорт"],
            "min_score": 5,
        }
        msg = _make_message("/mytopics", user_id=42)
        await handlers.cmd_mytopics(msg)
        text = msg.answer.call_args[0][0]
        assert "крипто" in text
        assert "спорт" in text
        assert "5" in text


class TestCmdMinscore:
    """Тесты /minscore."""

    @pytest.mark.asyncio
    async def test_minscore_no_args(self, admin_deps):
        msg = _make_message("/minscore", user_id=42)
        await handlers.cmd_minscore(msg)
        assert "Текущий минимальный балл" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_minscore_set_valid(self, admin_deps):
        msg = _make_message("/minscore 5", user_id=42)
        await handlers.cmd_minscore(msg)
        assert "установлен: 5" in msg.answer.call_args[0][0]
        admin_deps["cache_manager"].set_user_prefs.assert_called_with("100", min_score=5)

    @pytest.mark.asyncio
    async def test_minscore_invalid(self, admin_deps):
        msg = _make_message("/minscore 15", user_id=42)
        await handlers.cmd_minscore(msg)
        assert "число от 1 до 10" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_minscore_non_numeric(self, admin_deps):
        msg = _make_message("/minscore abc", user_id=42)
        await handlers.cmd_minscore(msg)
        assert "число от 1 до 10" in msg.answer.call_args[0][0]


class TestCmdSettings:
    """Тесты /settings."""

    @pytest.mark.asyncio
    async def test_settings_sends_keyboard(self, admin_deps):
        msg = _make_message("/settings", user_id=42)
        await handlers.cmd_settings(msg)
        msg.answer.assert_called_once()
        assert msg.answer.call_args[1].get("reply_markup") is not None


class TestCmdHealth:
    """Тесты /health."""

    @pytest.mark.asyncio
    async def test_health_returns_status(self, admin_deps):
        msg = _make_message("/health", user_id=42)
        await handlers.cmd_health(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Health" in text
        assert "ЗДОРОВ" in text


# ─── Callback handlers ───────────────────────────────────────────────────


class TestCbPostNow:
    """Тесты callback post_now."""

    @pytest.mark.asyncio
    async def test_cb_post_now(self, admin_deps):
        cb = _make_callback("post_now", user_id=42)
        await handlers.cb_post_now(cb)
        cb.answer.assert_called_once()
        admin_deps["job_collect_news"].assert_called_once()


class TestCbStats:
    """Тесты callback stats."""

    @pytest.mark.asyncio
    async def test_cb_stats(self, admin_deps):
        cb = _make_callback("stats", user_id=42)
        await handlers.cb_stats(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbTop:
    """Тесты callback top."""

    @pytest.mark.asyncio
    async def test_cb_top_empty(self, admin_deps):
        cb = _make_callback("top", user_id=42)
        await handlers.cb_top(cb)
        cb.answer.assert_called_once()


class TestCbAnalytics:
    """Тесты callback analytics."""

    @pytest.mark.asyncio
    async def test_cb_analytics(self, admin_deps):
        cb = _make_callback("analytics", user_id=42)
        await handlers.cb_analytics(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbABResults:
    """Тесты callback ab_results."""

    @pytest.mark.asyncio
    async def test_cb_ab_results(self, admin_deps):
        cb = _make_callback("ab_results", user_id=42)
        await handlers.cb_ab_results(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbABWinner:
    """Тесты callback ab_winner."""

    @pytest.mark.asyncio
    async def test_cb_ab_winner(self, admin_deps):
        cb = _make_callback("ab_winner", user_id=42)
        await handlers.cb_ab_winner(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbMetrics:
    """Тесты callback metrics."""

    @pytest.mark.asyncio
    async def test_cb_metrics(self, admin_deps):
        with patch("utils.metrics.collector") as mock_collector:
            mock_collector.get_report_text.return_value = "<b>Metrics</b>"
            cb = _make_callback("metrics", user_id=42)
            await handlers.cb_metrics(cb)
            cb.answer.assert_called_once()
            cb.message.answer.assert_called_once()


class TestCbAICost:
    """Тесты callback ai_cost."""

    @pytest.mark.asyncio
    async def test_cb_ai_cost(self, admin_deps):
        cb = _make_callback("ai_cost", user_id=42)
        await handlers.cb_ai_cost(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbHelp:
    """Тесты callback help."""

    @pytest.mark.asyncio
    async def test_cb_help(self, admin_deps):
        cb = _make_callback("help", user_id=42)
        await handlers.cb_help(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbStartMenu:
    """Тесты callback start_menu."""

    @pytest.mark.asyncio
    async def test_cb_start_menu(self, admin_deps):
        cb = _make_callback("start_menu", user_id=42)
        await handlers.cb_start_menu(cb)
        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert cb.message.edit_text.call_args[1].get("reply_markup") is not None


class TestCbSettingsMenu:
    """Тесты callback settings_menu."""

    @pytest.mark.asyncio
    async def test_cb_settings_menu(self, admin_deps):
        cb = _make_callback("settings_menu", user_id=42)
        await handlers.cb_settings_menu(cb)
        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert cb.message.edit_text.call_args[1].get("reply_markup") is not None


class TestCbTopicToggle:
    """Тесты callback topic_toggle."""

    @pytest.mark.asyncio
    async def test_cb_topic_toggle_subscribe(self, admin_deps):
        cb = _make_callback("topic_toggle:крипто", user_id=42)
        await handlers.cb_topic_toggle(cb)
        cb.answer.assert_called_once()
        assert "Подписались" in cb.answer.call_args[0][0]
        cb.message.edit_reply_markup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cb_topic_toggle_unsubscribe(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": ["крипто"],
            "blocked_topics": [],
            "min_score": 1,
        }
        cb = _make_callback("topic_toggle:крипто", user_id=42)
        await handlers.cb_topic_toggle(cb)
        assert "Отписались" in cb.answer.call_args[0][0]


class TestCbBlockToggle:
    """Тесты callback block_toggle."""

    @pytest.mark.asyncio
    async def test_cb_block_toggle_block(self, admin_deps):
        cb = _make_callback("block_toggle:спорт", user_id=42)
        await handlers.cb_block_toggle(cb)
        cb.answer.assert_called_once()
        assert "Заблокировали" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cb_block_toggle_unblock(self, admin_deps):
        admin_deps["cache_manager"].get_user_prefs.return_value = {
            "preferred_topics": [],
            "blocked_topics": ["спорт"],
            "min_score": 1,
        }
        cb = _make_callback("block_toggle:спорт", user_id=42)
        await handlers.cb_block_toggle(cb)
        assert "Разблокировали" in cb.answer.call_args[0][0]


class TestCbMinscoreMenu:
    """Тесты callback minscore_menu."""

    @pytest.mark.asyncio
    async def test_cb_minscore_menu(self, admin_deps):
        cb = _make_callback("minscore_menu", user_id=42)
        await handlers.cb_minscore_menu(cb)
        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert cb.message.edit_text.call_args[1].get("reply_markup") is not None


class TestCbMinscoreSet:
    """Тесты callback minscore_set."""

    @pytest.mark.asyncio
    async def test_cb_minscore_set(self, admin_deps):
        cb = _make_callback("minscore_set:7", user_id=42)
        await handlers.cb_minscore_set(cb)
        assert cb.answer.call_count == 2
        assert "7" in cb.answer.call_args_list[0][0][0]
        admin_deps["cache_manager"].set_user_prefs.assert_called_with("100", min_score=7)


class TestCbReaction:
    """Тесты callback react:."""

    @pytest.mark.asyncio
    async def test_cb_reaction_like(self, admin_deps):
        admin_deps["reactions_manager"].add_reaction.return_value = {
            "action": "added",
            "reaction_type": "like",
            "like": 1,
            "dislike": 0,
            "save": 0,
        }
        with patch("telegram_bot.poster._build_reactions_keyboard", create=True) as mock_kb:
            mock_kb.return_value = MagicMock()
            cb = _make_callback("react:like:12345", user_id=42)
            await handlers.cb_reaction(cb)
            assert cb.answer.call_count >= 1
            assert "👍" in cb.answer.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_cb_reaction_error_format(self, admin_deps):
        cb = _make_callback("react:like", user_id=42)  # неправильный формат
        await handlers.cb_reaction(cb)
        cb.answer.assert_called_once()
        assert "Ошибка формата" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cb_reaction_manager_error(self, admin_deps):
        admin_deps["reactions_manager"].add_reaction.return_value = {"error": "already reacted"}
        cb = _make_callback("react:like:12345", user_id=42)
        await handlers.cb_reaction(cb)
        cb.answer.assert_called_once()
        assert "already reacted" in cb.answer.call_args[0][0]


# ─── Register handlers ─────────────────────────────────────────────────────


class TestRegisterHandlers:
    """Тесты register_handlers."""

    def test_register_updates_deps(self):
        dp = MagicMock()
        dp.message = MagicMock()
        dp.callback_query = MagicMock()
        dp.message.register = MagicMock()
        dp.callback_query.register = MagicMock()

        deps = {"ADMIN_ID": 42, "config": MagicMock()}
        handlers.register_handlers(dp, **deps)

        assert handlers._deps["ADMIN_ID"] == 42
        # Проверяем, что зарегистрированы message handlers
        assert dp.message.register.call_count >= 15
        # Проверяем, что зарегистрированы callback handlers
        assert dp.callback_query.register.call_count >= 10
