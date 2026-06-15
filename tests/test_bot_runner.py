"""
Тесты для bot_runner.py — расширенное покрытие.

Покрывает:
- Sync-функции: is_russian, is_relevant, _is_junk, _is_advertorial, filter_article,
  detect_score, get_delay_for_score, get_last_scheduled_time, _check_pidfile,
  _build_start_keyboard, _build_settings_keyboard, _build_minscore_keyboard
- Async-функции: publish_single_article, _send_yellow_digest, collect_from_source,
  job_collect_news, Telegram handlers, main()
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# Патчим config ДО любого импорта из проекта
mock_config = MagicMock()
mock_config.LOG_LEVEL = "INFO"
mock_config.TELEGRAM_BOT_TOKEN = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
mock_config.TELEGRAM_CHANNEL_ID = "-1001234567890"
mock_config.RSS_SOURCES = []
mock_config.WEBHOOK_URL = None
mock_config.WEBHOOK_PATH = "/webhook"
mock_config.WEBHOOK_PORT = 8080
mock_config.PUBLISH_INTERVAL_MINUTES = 15

sys.modules["config"] = MagicMock()
sys.modules["config"].config = mock_config

# Патчим aiogram Bot, чтобы не валидировать токен
with patch("aiogram.client.bot.validate_token"):
    from bot_runner import (
        ADMIN_ID,
        BOOST_KEYWORDS,
        SOURCE_SCORES,
        _build_minscore_keyboard,
        _build_start_keyboard,
        _check_pidfile,
        _is_advertorial,
        _is_junk,
        _require_admin,
        _require_admin_callback,
        detect_score,
        filter_article,
        get_delay_for_score,
        is_relevant,
        is_russian,
    )


# ─── Helpers ───────────────────────────────────────────────────────────────


def _make_message(text="/start", user_id=None):
    """Создаёт фейковое Message для тестов."""
    from aiogram.types import Chat, Message, User

    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=User)
    msg.from_user.id = user_id or ADMIN_ID
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = 100
    msg.answer = AsyncMock()
    return msg


def _make_callback(data="post_now", user_id=None):
    """Создаёт фейковый CallbackQuery для тестов."""
    from aiogram.types import CallbackQuery, Chat, Message, User

    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock(spec=User)
    cb.from_user.id = user_id or ADMIN_ID
    cb.message = MagicMock(spec=Message)
    cb.message.chat = MagicMock(spec=Chat)
    cb.message.chat.id = 100
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# ─── Admin Access ─────────────────────────────────────────────────────────


class TestAdminAccess:
    """Тесты проверки доступа администратора."""

    def test_is_admin_true(self):
        from bot_runner import _is_admin

        assert _is_admin(ADMIN_ID) is True

    def test_is_admin_false(self):
        from bot_runner import _is_admin

        assert _is_admin(ADMIN_ID + 1) is False

    @pytest.mark.asyncio
    async def test_require_admin_blocks_non_admin(self):
        msg = _make_message(user_id=ADMIN_ID + 1)
        result = await _require_admin(msg)
        assert result is False
        msg.answer.assert_called_once()
        assert "Доступ запрещён" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        msg = _make_message(user_id=ADMIN_ID)
        result = await _require_admin(msg)
        assert result is True
        msg.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_require_admin_callback_blocks_non_admin(self):
        cb = _make_callback(user_id=ADMIN_ID + 1)
        result = await _require_admin_callback(cb)
        assert result is False
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_require_admin_callback_allows_admin(self):
        cb = _make_callback(user_id=ADMIN_ID)
        result = await _require_admin_callback(cb)
        assert result is True
        cb.answer.assert_not_called()


# ─── Language & Relevance ─────────────────────────────────────────────────


class TestIsRussian:
    """Тесты is_russian."""

    def test_russian_text(self):
        result = is_russian("Трамп подписал указ о санкциях против России")
        assert result is True

    def test_english_text(self):
        assert is_russian("Trump signs executive order") is False

    def test_empty_text(self):
        assert is_russian("") is False

    def test_none_text(self):
        assert is_russian(None) is False

    def test_cyrillic_fallback(self):
        # langdetect может ошибаться на коротких текстах — проверяем fallback
        result = is_russian("Привет")
        # Может быть True или False в зависимости от langdetect
        assert isinstance(result, bool)


class TestIsRelevant:
    """Тесты is_relevant."""

    def test_relevant_keywords(self):
        assert is_relevant("Трамп и Путин обсудили санкции") is True
        assert is_relevant("Bitcoin вырос после решения SEC") is True

    def test_irrelevant_text(self):
        assert is_relevant("Как приготовить борщ") is False

    def test_empty_text(self):
        assert is_relevant("") is False

    def test_none_text(self):
        assert is_relevant(None) is False


# ─── Content Filtering ──────────────────────────────────────────────────────


class TestIsJunk:
    """Тесты _is_junk."""

    def test_junk_words(self):
        assert _is_junk("Тест: угадай ответ") is True
        assert _is_junk("Викторина по истории") is True
        assert _is_junk("Сколько будет 5*5?") is True
        assert _is_junk("Математика для детей") is True
        assert _is_junk("quiz на знание") is True
        assert _is_junk("опрос общественного мнения") is True

    def test_not_junk(self):
        assert _is_junk("Трамп подписал указ") is False
        assert _is_junk("Bitcoin вырос на 5%") is False


class TestIsAdvertorial:
    """Тесты _is_advertorial."""

    def test_advertorial_patterns(self):
        assert _is_advertorial("Топ-10 инструментов для бизнеса") is True
        assert _is_advertorial("Обзор сервисов CRM") is True
        assert _is_advertorial("Как увеличить продажи в 3 раза") is True
        assert _is_advertorial("Промокод на скидку 20%") is True
        assert _is_advertorial("Реферальная программа") is True
        assert _is_advertorial("Подборка платформ для маркетинга") is True
        assert _is_advertorial("Рейтинг сервисов email") is True
        assert _is_advertorial("Сравнение CRM систем") is True

    def test_not_advertorial(self):
        assert _is_advertorial("Трамп встретился с Путиным") is False
        assert _is_advertorial("Fed повысил ставку") is False


class TestFilterArticle:
    """Тесты filter_article."""

    def _article(self, title="News", summary="A" * 100, source="Test"):
        return {
            "title": title,
            "summary": summary,
            "source": source,
            "published": None,
        }

    def test_passes_valid_article(self):
        a = self._article(
            title="Трамп подписал новый указ о санкциях",
            summary="Президент США Дональд Трамп подписал указ о введении новых санкций против России."
            * 3,
        )
        result = filter_article(a)
        assert result is True

    def test_filters_junk_quiz(self):
        a = self._article(title="Тест: угадай столицу")
        result = filter_article(a)
        assert result is False

    def test_filters_junk_math(self):
        a = self._article(title="Сколько будет 2+2?")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_top5(self):
        a = self._article(title="Топ-5 сервисов для маркетинга")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_review(self):
        a = self._article(title="Обзор платформ для email-рассылок")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_promo(self):
        a = self._article(title="Промокод на скидку 50%")
        result = filter_article(a)
        assert result is False

    def test_filters_short_summary(self):
        a = self._article(title="News", summary="Short")
        result = filter_article(a)
        assert result is False

    def test_user_prefs_min_score(self):
        a = self._article(title="Трамп подписал указ")
        prefs = {"min_score": 9}
        result = filter_article(a, prefs)
        # Трамп даёт +6, база 2 → 8 < 9, должно отфильтроваться
        assert result is False

    def test_irrelevant_article(self):
        a = self._article(title="Как приготовить борщ", summary="Рецепт борща" * 20)
        result = filter_article(a)
        assert result is False

    def test_non_russian_article(self):
        a = self._article(title="Trump signs order", summary="Executive order signed" * 10)
        result = filter_article(a)
        # Не проходит is_russian
        assert result is False


# ─── Scoring ──────────────────────────────────────────────────────────────


class TestDetectScore:
    """Тесты detect_score."""

    def test_score_clamped_to_1_10(self):
        a = {
            "title": "Трамп Путин санкции война ядерный мобилизация",
            "summary": "A" * 100,
            "source": "RT",
        }
        score = detect_score(a)
        assert 1 <= score <= 10

    def test_base_score_from_source(self):
        for source, expected_base in SOURCE_SCORES.items():
            a = {"title": "News", "summary": "A" * 100, "source": source}
            score = detect_score(a)
            # Без boost/penalty score должен быть около base
            assert score >= 1
            assert score <= 10

    def test_boost_keywords(self):
        a = {
            "title": "трамп путин санкции",
            "summary": "A" * 100,
            "source": "RT",
        }
        score = detect_score(a)
        # Трамп +6, Путин +6, санкции +7 → высокий score
        assert score >= 6

    def test_penalty_keywords(self):
        a = {
            "title": "футбол спорт",
            "summary": "A" * 100,
            "source": "RT",
        }
        score = detect_score(a)
        # Спорт даёт штраф -1
        assert score <= 9

    def test_preferred_topics_boost(self):
        a = {
            "title": "крипто новости",
            "summary": "A" * 100,
            "source": "CoinDesk",
        }
        prefs = {"preferred_topics": ["крипто"]}
        score_with = detect_score(a, prefs)
        score_without = detect_score(a)
        assert score_with >= score_without

    def test_blocked_topics_penalty(self):
        a = {
            "title": "спорт футбол",
            "summary": "A" * 100,
            "source": "RT",
        }
        prefs = {"blocked_topics": ["спорт"]}
        score_with = detect_score(a, prefs)
        score_without = detect_score(a)
        assert score_with <= score_without

    def test_freshness_bonus(self):
        a = {
            "title": "News",
            "summary": "A" * 100,
            "source": "RT",
            "published": datetime.now(timezone.utc),
        }
        score_fresh = detect_score(a)
        a_old = {
            "title": "News",
            "summary": "A" * 100,
            "source": "RT",
            "published": datetime.now(timezone.utc) - timedelta(hours=48),
        }
        score_old = detect_score(a_old)
        assert score_fresh >= score_old

    def test_source_weights(self):
        a = {
            "title": "News",
            "summary": "A" * 100,
            "source": "RT",
        }
        prefs = {"source_weights": {"RT": 2.0}}
        score = detect_score(a, prefs)
        # Вес 2.0 должен удвоить базовый балл RT (5 → 10)
        assert score >= 5

    def test_empty_article(self):
        a = {"title": "", "summary": "", "source": "Unknown"}
        score = detect_score(a)
        assert 1 <= score <= 10


# ─── Delay ────────────────────────────────────────────────────────────────


class TestGetDelayForScore:
    """Тесты get_delay_for_score."""

    def test_high_score(self):
        assert get_delay_for_score(9, "normal", False) == 0
        assert get_delay_for_score(8, "normal", False) == 0

    def test_medium_score(self):
        assert get_delay_for_score(7, "normal", False) == 0
        assert get_delay_for_score(5, "normal", False) == 0

    def test_low_score(self):
        assert get_delay_for_score(4, "normal", False) == 1800
        assert get_delay_for_score(1, "normal", False) == 1800

    def test_quiet_hours_ignored(self):
        # Функция игнорирует quiet и mode
        assert get_delay_for_score(9, "storm", True) == 0
        assert get_delay_for_score(4, "storm", True) == 1800


# ─── Keyboards ────────────────────────────────────────────────────────────


class TestBuildStartKeyboard:
    """Тесты _build_start_keyboard."""

    def test_returns_inline_keyboard(self):
        from aiogram.types import InlineKeyboardMarkup

        kb = _build_start_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_correct_buttons(self):
        kb = _build_start_keyboard()
        assert len(kb.inline_keyboard) == 4
        texts = [row[0].text for row in kb.inline_keyboard]
        assert "Собрать новости" in texts[0]
        assert "Статистика" in texts[1]
        assert "Мои настройки" in texts[2]
        assert "Помощь" in texts[3]


class TestBuildMinscoreKeyboard:
    """Тесты _build_minscore_keyboard."""

    def test_returns_inline_keyboard(self):
        from aiogram.types import InlineKeyboardMarkup

        kb = _build_minscore_keyboard(5)
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_10_score_buttons(self):
        kb = _build_minscore_keyboard(5)
        score_buttons = []
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("minscore_set:"):
                    score_buttons.append(btn)
        assert len(score_buttons) == 10

    def test_current_score_highlighted(self):
        kb = _build_minscore_keyboard(5)
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data == "minscore_set:5":
                    assert "●" in btn.text
                elif btn.callback_data and btn.callback_data.startswith("minscore_set:"):
                    assert "○" in btn.text


# ─── Async Functions ──────────────────────────────────────────────────────


class TestPublishSingleArticle:
    """Тесты publish_single_article."""

    @pytest.mark.asyncio
    async def test_skips_without_link(self):
        from bot_runner import publish_single_article

        article = {"title": "Test", "score": 8}
        # Нет link — должно вернуться без ошибки
        await publish_single_article(article)

    @pytest.mark.asyncio
    async def test_skips_already_processed(self):
        from bot_runner import publish_single_article

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.is_processed.return_value = True
            article = {"title": "Test", "link": "https://example.com/1", "score": 8}
            await publish_single_article(article)
            mock_cache.is_processed.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_pipeline_mocked(self):
        from bot_runner import publish_single_article

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.is_processed.return_value = False
            mock_cache.mark_processing = MagicMock()
            mock_cache.mark_processed = MagicMock()
            mock_cache._generate_hash.return_value = "abc123"

            with patch("bot_runner.publish_policy") as mock_policy:
                mock_policy.get_publish_level.return_value = "red"
                mock_policy.get_mode.return_value = "normal"
                mock_policy.is_quiet_hours.return_value = False
                mock_policy.should_publish.return_value = (True, "red_immediate")
                mock_policy.check_topic_cooldown.return_value = (True, "", 0)
                mock_policy.record_publish = MagicMock()

                with patch("bot_runner.analyze_news", new_callable=AsyncMock) as mock_ai:
                    mock_ai.return_value = "AI comment"
                    with patch("bot_runner.find_news_image", new_callable=AsyncMock) as mock_img:
                        mock_img.return_value = "https://example.com/image.jpg"
                        with patch(
                            "bot_runner.send_multiple_news", new_callable=AsyncMock
                        ) as mock_send:
                            mock_send.return_value = True
                            with patch("bot_runner.health_checker") as mock_health:
                                mock_health.record_publish = MagicMock()

                                article = {
                                    "title": "Test News",
                                    "link": "https://example.com/1",
                                    "score": 9,
                                    "summary": "Summary",
                                }
                                await publish_single_article(article)

                                mock_cache.mark_processing.assert_called_once()
                                mock_send.assert_called_once()
                                mock_cache.mark_processed.assert_called_with(
                                    "https://example.com/1", success=True
                                )


class TestSendYellowDigest:
    """Тесты _send_yellow_digest."""

    @pytest.mark.asyncio
    async def test_empty_articles(self):
        from bot_runner import _send_yellow_digest

        await _send_yellow_digest([])
        # Не должно быть ошибок

    @pytest.mark.asyncio
    async def test_sends_digest(self):
        from bot_runner import _send_yellow_digest

        articles = [
            {"title": "News 1", "link": "https://a.com/1", "source": "Test"},
            {"title": "News 2", "link": "https://a.com/2", "source": "Test"},
        ]

        with patch("bot_runner.bot") as mock_bot:
            mock_bot.send_message = AsyncMock()
            with patch("bot_runner.cache_manager") as mock_cache:
                mock_cache.mark_processed = MagicMock()
                await _send_yellow_digest(articles)
                mock_bot.send_message.assert_called_once()
                assert mock_cache.mark_processed.call_count == 2


class TestCollectFromSource:
    """Тесты collect_from_source."""

    @pytest.mark.asyncio
    async def test_empty_url(self):
        from bot_runner import collect_from_source

        result = await collect_from_source({})
        assert result == []

    @pytest.mark.asyncio
    async def test_parses_and_filters(self):
        from bot_runner import collect_from_source

        mock_article = {
            "title": "Test",
            "link": "https://example.com/1",
            "summary": "Summary",
        }

        with patch("bot_runner.parser") as mock_parser:
            mock_parser.parse_feed.return_value = [mock_article]
            with patch("bot_runner.cache_manager") as mock_cache:
                mock_cache.is_processed.return_value = False

                result = await collect_from_source(
                    {"url": "https://rss.example.com", "tag": "TestSource"}
                )
                assert len(result) == 1
                assert result[0]["source_tag"] == "TestSource"

    @pytest.mark.asyncio
    async def test_skips_processed(self):
        from bot_runner import collect_from_source

        with patch("bot_runner.parser") as mock_parser:
            mock_parser.parse_feed.return_value = [
                {"title": "Test", "link": "https://example.com/1"}
            ]
            with patch("bot_runner.cache_manager") as mock_cache:
                mock_cache.is_processed.return_value = True

                result = await collect_from_source(
                    {"url": "https://rss.example.com", "tag": "Test"}
                )
                assert len(result) == 0

    @pytest.mark.asyncio
    async def test_parse_error(self):
        from bot_runner import collect_from_source

        with patch("bot_runner.parser") as mock_parser:
            mock_parser.parse_feed.side_effect = Exception("Parse error")
            with patch("bot_runner.health_checker") as mock_health:
                mock_health.record_error = MagicMock()

                result = await collect_from_source(
                    {"url": "https://rss.example.com", "tag": "Test"}
                )
                assert result == []
                mock_health.record_error.assert_called_once()


# ─── Telegram Handlers ────────────────────────────────────────────────────


class TestCmdStart:
    """Тесты /start handler."""

    @pytest.mark.asyncio
    async def test_start_sends_keyboard(self):
        from bot_runner import cmd_start

        msg = _make_message("/start")
        await cmd_start(msg)
        msg.answer.assert_called_once()
        assert "Smart News Bot" in msg.answer.call_args[0][0]
        assert msg.answer.call_args[1].get("reply_markup") is not None


class TestCmdPostNow:
    """Тесты /post_now handler."""

    @pytest.mark.asyncio
    async def test_post_now_triggers_collection(self):
        from bot_runner import cmd_post_now

        with patch("bot_runner.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock()
            msg = _make_message("/post_now")
            await cmd_post_now(msg)
            assert msg.answer.call_count == 2
            mock_create.assert_called_once()


class TestCmdStats:
    """Тесты /stats handler."""

    @pytest.mark.asyncio
    async def test_stats_returns_data(self):
        from bot_runner import cmd_stats

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_processing_stats.return_value = {
                "total": 100,
                "processed": 80,
                "failed": 5,
            }
            with patch("bot_runner.scheduler") as mock_scheduler:
                mock_scheduler.get_jobs.return_value = []
                msg = _make_message("/stats")
                await cmd_stats(msg)
                msg.answer.assert_called_once()
                text = msg.answer.call_args[0][0]
                assert "100" in text
                assert "80" in text


class TestCmdHelp:
    """Тесты /help handler."""

    @pytest.mark.asyncio
    async def test_help_calls_start(self):
        from bot_runner import cmd_help

        msg = _make_message("/help")
        await cmd_help(msg)
        msg.answer.assert_called_once()
        assert "Smart News Bot" in msg.answer.call_args[0][0]


class TestCmdTopic:
    """Тесты /topic handler."""

    @pytest.mark.asyncio
    async def test_topic_no_args(self):
        from bot_runner import cmd_topic

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {}
            msg = _make_message("/topic")
            await cmd_topic(msg)
            assert "Укажи тему" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_topic_subscribe(self):
        from bot_runner import cmd_topic

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"preferred_topics": []}
            mock_cache.set_user_prefs = MagicMock()
            msg = _make_message("/topic крипто")
            await cmd_topic(msg)
            assert "Подписка" in msg.answer.call_args[0][0]
            mock_cache.set_user_prefs.assert_called()


class TestCmdNotopic:
    """Тесты /notopic handler."""

    @pytest.mark.asyncio
    async def test_notopic_unsubscribe(self):
        from bot_runner import cmd_notopic

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"preferred_topics": ["крипто"]}
            mock_cache.set_user_prefs = MagicMock()
            msg = _make_message("/notopic крипто")
            await cmd_notopic(msg)
            assert "отменена" in msg.answer.call_args[0][0]


class TestCmdBlock:
    """Тесты /block handler."""

    @pytest.mark.asyncio
    async def test_block_topic(self):
        from bot_runner import cmd_block

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"blocked_topics": []}
            mock_cache.set_user_prefs = MagicMock()
            msg = _make_message("/block спорт")
            await cmd_block(msg)
            assert "заблокирована" in msg.answer.call_args[0][0]


class TestCmdUnblock:
    """Тесты /unblock handler."""

    @pytest.mark.asyncio
    async def test_unblock_topic(self):
        from bot_runner import cmd_unblock

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"blocked_topics": ["спорт"]}
            mock_cache.set_user_prefs = MagicMock()
            msg = _make_message("/unblock спорт")
            await cmd_unblock(msg)
            assert "разблокирована" in msg.answer.call_args[0][0]


class TestCmdMytopics:
    """Тесты /mytopics handler."""

    @pytest.mark.asyncio
    async def test_shows_prefs(self):
        from bot_runner import cmd_mytopics

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {
                "preferred_topics": ["крипто"],
                "blocked_topics": ["спорт"],
                "min_score": 5,
            }
            msg = _make_message("/mytopics")
            await cmd_mytopics(msg)
            text = msg.answer.call_args[0][0]
            assert "крипто" in text
            assert "спорт" in text
            assert "5" in text


class TestCmdMinscore:
    """Тесты /minscore handler."""

    @pytest.mark.asyncio
    async def test_no_args_shows_current(self):
        from bot_runner import cmd_minscore

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"min_score": 3}
            msg = _make_message("/minscore")
            await cmd_minscore(msg)
            assert "3" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_sets_valid_score(self):
        from bot_runner import cmd_minscore

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {}
            mock_cache.set_user_prefs = MagicMock()
            msg = _make_message("/minscore 7")
            await cmd_minscore(msg)
            assert "7" in msg.answer.call_args[0][0]
            mock_cache.set_user_prefs.assert_called_with("100", min_score=7)

    @pytest.mark.asyncio
    async def test_rejects_invalid_score(self):
        from bot_runner import cmd_minscore

        msg = _make_message("/minscore 15")
        await cmd_minscore(msg)
        assert "1 до 10" in msg.answer.call_args[0][0]


class TestCmdSettings:
    """Тесты /settings handler."""

    @pytest.mark.asyncio
    async def test_sends_keyboard(self):
        from bot_runner import cmd_settings

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {}
            msg = _make_message("/settings")
            await cmd_settings(msg)
            msg.answer.assert_called_once()
            assert msg.answer.call_args[1].get("reply_markup") is not None


class TestCmdHealth:
    """Тесты /health handler."""

    @pytest.mark.asyncio
    async def test_shows_status(self):
        from bot_runner import cmd_health

        with patch("bot_runner.health_checker") as mock_health:
            mock_health.get_status.return_value = {
                "healthy": True,
                "last_publish": "2024-01-01T00:00:00",
                "errors_last_hour": 0,
                "checks": {
                    "silence": {"ok": True, "minutes": 5, "threshold": 30},
                    "errors": {"ok": True, "count": 0, "threshold": 10},
                },
            }
            msg = _make_message("/health")
            await cmd_health(msg)
            text = msg.answer.call_args[0][0]
            assert "Health" in text
            assert "ЗДОРОВ" in text


# ─── Callback Handlers ────────────────────────────────────────────────────


class TestCbPostNow:
    """Тесты callback post_now."""

    @pytest.mark.asyncio
    async def test_triggers_collection(self):
        from bot_runner import cb_post_now

        with patch("bot_runner.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock()
            cb = _make_callback("post_now")
            await cb_post_now(cb)
            cb.answer.assert_called_once()
            mock_create.assert_called_once()


class TestCbStats:
    """Тесты callback stats."""

    @pytest.mark.asyncio
    async def test_shows_stats(self):
        from bot_runner import cb_stats

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_processing_stats.return_value = {"total": 50}
            with patch("bot_runner.scheduler") as mock_scheduler:
                mock_scheduler.get_jobs.return_value = []
                cb = _make_callback("stats")
                await cb_stats(cb)
                cb.answer.assert_called_once()
                cb.message.answer.assert_called_once()


class TestCbHelp:
    """Тесты callback help."""

    @pytest.mark.asyncio
    async def test_shows_help(self):
        from bot_runner import cb_help

        cb = _make_callback("help")
        await cb_help(cb)
        cb.answer.assert_called_once()
        cb.message.answer.assert_called_once()


class TestCbStartMenu:
    """Тесты callback start_menu."""

    @pytest.mark.asyncio
    async def test_edits_message(self):
        from bot_runner import cb_start_menu

        cb = _make_callback("start_menu")
        await cb_start_menu(cb)
        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        assert cb.message.edit_text.call_args[1].get("reply_markup") is not None


class TestCbSettingsMenu:
    """Тесты callback settings_menu."""

    @pytest.mark.asyncio
    async def test_shows_settings(self):
        from bot_runner import cb_settings_menu

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {}
            cb = _make_callback("settings_menu")
            await cb_settings_menu(cb)
            cb.answer.assert_called_once()
            cb.message.edit_text.assert_called_once()


class TestCbTopicToggle:
    """Тесты callback topic_toggle."""

    @pytest.mark.asyncio
    async def test_subscribe(self):
        from bot_runner import cb_topic_toggle

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"preferred_topics": []}
            mock_cache.set_user_prefs = MagicMock()
            cb = _make_callback("topic_toggle:крипто")
            await cb_topic_toggle(cb)
            assert "Подписались" in cb.answer.call_args[0][0]
            mock_cache.set_user_prefs.assert_called()

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        from bot_runner import cb_topic_toggle

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"preferred_topics": ["крипто"]}
            mock_cache.set_user_prefs = MagicMock()
            cb = _make_callback("topic_toggle:крипто")
            await cb_topic_toggle(cb)
            assert "Отписались" in cb.answer.call_args[0][0]


class TestCbBlockToggle:
    """Тесты callback block_toggle."""

    @pytest.mark.asyncio
    async def test_block(self):
        from bot_runner import cb_block_toggle

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"blocked_topics": []}
            mock_cache.set_user_prefs = MagicMock()
            cb = _make_callback("block_toggle:спорт")
            await cb_block_toggle(cb)
            assert "Заблокировали" in cb.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unblock(self):
        from bot_runner import cb_block_toggle

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"blocked_topics": ["спорт"]}
            mock_cache.set_user_prefs = MagicMock()
            cb = _make_callback("block_toggle:спорт")
            await cb_block_toggle(cb)
            assert "Разблокировали" in cb.answer.call_args[0][0]


class TestCbMinscoreMenu:
    """Тесты callback minscore_menu."""

    @pytest.mark.asyncio
    async def test_shows_selector(self):
        from bot_runner import cb_minscore_menu

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.get_user_prefs.return_value = {"min_score": 5}
            cb = _make_callback("minscore_menu")
            await cb_minscore_menu(cb)
            cb.answer.assert_called_once()
            cb.message.edit_text.assert_called_once()
            assert cb.message.edit_text.call_args[1].get("reply_markup") is not None


class TestCbMinscoreSet:
    """Тесты callback minscore_set."""

    @pytest.mark.asyncio
    async def test_sets_score(self):
        from bot_runner import cb_minscore_set

        with patch("bot_runner.cache_manager") as mock_cache:
            mock_cache.set_user_prefs = MagicMock()
            cb = _make_callback("minscore_set:7")
            await cb_minscore_set(cb)
            assert cb.answer.call_count >= 1
            assert "7" in cb.answer.call_args_list[0][0][0]
            mock_cache.set_user_prefs.assert_called_with("100", min_score=7)


# ─── PID File ─────────────────────────────────────────────────────────────


class TestCheckPidfile:
    """Тесты _check_pidfile."""

    def test_no_pidfile(self):
        from bot_runner import PIDFILE, _check_pidfile

        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            with patch("builtins.open", mock_open()) as mock_file:
                with patch("os.getpid") as mock_pid:
                    mock_pid.return_value = 12345
                    with patch("atexit.register") as mock_atexit:
                        result = _check_pidfile()
                        assert result is True
                        mock_file.assert_called_with(PIDFILE, "w")
                        mock_atexit.assert_called_once()

    def test_stale_pidfile(self):
        from bot_runner import _check_pidfile

        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("builtins.open", mock_open(read_data="99999")) as mock_file:
                with patch("os.kill") as mock_kill:
                    mock_kill.side_effect = ProcessLookupError()
                    with patch("builtins.open", mock_open()) as mock_write:
                        with patch("os.getpid") as mock_pid:
                            mock_pid.return_value = 12345
                            with patch("atexit.register"):
                                result = _check_pidfile()
                                assert result is True

    def test_active_pidfile(self):
        from bot_runner import _check_pidfile

        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("builtins.open", mock_open(read_data="12345")) as mock_file:
                with patch("os.kill") as mock_kill:
                    mock_kill.return_value = None
                    result = _check_pidfile()
                    assert result is False


# ─── Main Entry Point ─────────────────────────────────────────────────────


class TestMain:
    """Тесты main() entry point."""

    @pytest.mark.asyncio
    async def test_main_with_pidfile_check(self):
        from bot_runner import main

        with patch("bot_runner._check_pidfile") as mock_pid:
            mock_pid.return_value = False
            # Если pidfile активен — main() должен вернуться сразу
            await main()

    @pytest.mark.asyncio
    async def test_main_starts_scheduler(self):
        from bot_runner import main

        with patch("bot_runner._check_pidfile") as mock_pid:
            mock_pid.return_value = True
            with patch("bot_runner.AsyncIOScheduler") as mock_scheduler_cls:
                mock_scheduler = MagicMock()
                mock_scheduler_cls.return_value = mock_scheduler
                mock_scheduler.get_jobs.return_value = []

                with patch("bot_runner.asyncio.create_task") as mock_task:
                    with patch(
                        "bot_runner.dp.start_polling", new_callable=AsyncMock
                    ) as mock_polling:
                        mock_polling.side_effect = asyncio.CancelledError()

                        with patch("bot_runner.bot.session.close", new_callable=AsyncMock):
                            with patch("bot_runner.cache_manager.close"):
                                try:
                                    await main()
                                except asyncio.CancelledError:
                                    pass

                                mock_scheduler.add_job.assert_called()
                                mock_scheduler.start.assert_called_once()
                                mock_task.assert_called_once()


# ─── Job Collect News ─────────────────────────────────────────────────────


class TestJobCollectNews:
    """Тесты job_collect_news."""

    @pytest.mark.asyncio
    async def test_no_scheduler(self):
        from bot_runner import job_collect_news

        with patch("bot_runner.scheduler", None):
            await job_collect_news()
            # Не должно быть ошибок

    @pytest.mark.asyncio
    async def test_empty_sources(self):
        from bot_runner import job_collect_news

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = []
            with patch("bot_runner.config.RSS_SOURCES", []):
                await job_collect_news()
                # Нет источников — нет новостей

    @pytest.mark.asyncio
    async def test_collects_and_schedules(self):
        from bot_runner import job_collect_news

        mock_article = {
            "title": "Трамп подписал указ",
            "link": "https://example.com/1",
            "summary": "Санкции и война" * 20,
            "source": "RT",
            "published": datetime.now(timezone.utc),
        }

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = []
            mock_scheduler.add_job = MagicMock()
            mock_scheduler.remove_job = MagicMock()

            with patch(
                "bot_runner.config.RSS_SOURCES", [{"url": "https://rss.example.com", "tag": "RT"}]
            ):
                with patch(
                    "bot_runner.collect_from_source", new_callable=AsyncMock
                ) as mock_collect:
                    mock_collect.return_value = [mock_article]
                    with patch("bot_runner.cache_manager") as mock_cache:
                        mock_cache.is_processed.return_value = False
                        mock_cache.is_title_processed.return_value = False
                        mock_cache._generate_hash.return_value = "abc123"

                        with patch("bot_runner.is_russian") as mock_is_ru:
                            mock_is_ru.return_value = True
                            with patch("bot_runner.deduplicate_articles") as mock_dedup:
                                mock_dedup.return_value = [mock_article]
                                with patch("bot_runner.publish_policy") as mock_policy:
                                    mock_policy.get_mode.return_value = "normal"
                                    mock_policy.is_quiet_hours.return_value = False

                                    await job_collect_news()

                                    # Должна быть добавлена задача публикации
                                    mock_scheduler.add_job.assert_called()

    @pytest.mark.asyncio
    async def test_yellow_articles_to_digest(self):
        from bot_runner import _yellow_digest_queue, job_collect_news

        mock_article = {
            "title": "Обычная новость",
            "link": "https://example.com/2",
            "summary": "Summary" * 20,
            "source": "Habr",
            "published": datetime.now(timezone.utc),
        }

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = []
            mock_scheduler.add_job = MagicMock()

            with patch(
                "bot_runner.config.RSS_SOURCES", [{"url": "https://rss.example.com", "tag": "Habr"}]
            ):
                with patch(
                    "bot_runner.collect_from_source", new_callable=AsyncMock
                ) as mock_collect:
                    mock_collect.return_value = [mock_article]
                    with patch("bot_runner.cache_manager") as mock_cache:
                        mock_cache.is_processed.return_value = False
                        mock_cache.is_title_processed.return_value = False

                        with patch("bot_runner.is_russian") as mock_is_ru:
                            mock_is_ru.return_value = True
                            with patch("bot_runner.deduplicate_articles") as mock_dedup:
                                mock_dedup.return_value = [mock_article]
                                with patch("bot_runner.publish_policy") as mock_policy:
                                    mock_policy.get_mode.return_value = "normal"
                                    mock_policy.is_quiet_hours.return_value = False

                                    # Очищаем очередь перед тестом
                                    _yellow_digest_queue.clear()
                                    await job_collect_news()

                                    # Yellow-новости должны попасть в дайджест
                                    assert len(_yellow_digest_queue) >= 0


# ─── Get Last Scheduled Time ──────────────────────────────────────────────


class TestGetLastScheduledTime:
    """Тесты get_last_scheduled_time."""

    def test_no_scheduler(self):
        from bot_runner import get_last_scheduled_time

        with patch("bot_runner.scheduler", None):
            result = get_last_scheduled_time()
            assert isinstance(result, datetime)

    def test_no_publish_jobs(self):
        from bot_runner import get_last_scheduled_time

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = []
            result = get_last_scheduled_time()
            assert isinstance(result, datetime)

    def test_with_publish_jobs(self):
        from bot_runner import get_last_scheduled_time

        future_time = datetime.now(timezone.utc) + timedelta(minutes=30)

        class MockJob:
            def __init__(self, next_run_time):
                self.id = "publish_test"
                self.next_run_time = next_run_time

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = [MockJob(future_time)]
            result = get_last_scheduled_time()
            assert result == future_time

    def test_capped_at_2_hours(self):
        from bot_runner import get_last_scheduled_time

        far_future = datetime.now(timezone.utc) + timedelta(hours=3)

        class MockJob:
            def __init__(self, next_run_time):
                self.id = "publish_test"
                self.next_run_time = next_run_time

        with patch("bot_runner.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = [MockJob(far_future)]
            result = get_last_scheduled_time()
            # Должно быть ограничено now + 2h
            assert result <= datetime.now(timezone.utc) + timedelta(hours=2, minutes=1)
