"""
Тесты для telegram_bot/keyboards.py
"""

from unittest.mock import MagicMock, patch

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.keyboards import (
    _PRESET_BLOCKED,
    _PRESET_TOPICS,
    build_minscore_keyboard,
    build_settings_keyboard,
    build_start_keyboard,
)


class TestBuildStartKeyboard:
    """Тесты для build_start_keyboard."""

    def test_returns_inline_keyboard_markup(self):
        kb = build_start_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_correct_number_of_buttons(self):
        kb = build_start_keyboard()
        # 10 кнопок, каждая в отдельном ряду
        assert len(kb.inline_keyboard) == 10
        for row in kb.inline_keyboard:
            assert len(row) == 1

    def test_button_texts_and_callbacks(self):
        kb = build_start_keyboard()
        buttons = [row[0] for row in kb.inline_keyboard]

        expected = [
            ("📰 Собрать новости", "post_now"),
            ("📊 Статистика", "stats"),
            ("🏆 Топ новостей", "top"),
            ("📈 Аналитика", "analytics"),
            ("🧪 A/B результаты", "ab_results"),
            ("🏅 A/B winner", "ab_winner"),
            ("📉 Метрики", "metrics"),
            ("🤖 AI стоимость", "ai_cost"),
            ("⚙️ Мои настройки", "settings_menu"),
            ("❓ Помощь", "help"),
        ]

        assert len(buttons) == len(expected)
        for btn, (text, callback) in zip(buttons, expected):
            assert btn.text == text
            assert btn.callback_data == callback


class TestBuildSettingsKeyboard:
    """Тесты для build_settings_keyboard."""

    @patch("telegram_bot.keyboards.cache_manager")
    def test_empty_prefs_shows_all_unchecked(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {}
        kb = build_settings_keyboard("123456")

        assert isinstance(kb, InlineKeyboardMarkup)
        # Проверяем, что кнопки тем подписки имеют ⬜ (не выбраны)
        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        crypto_btn = next((btn for btn in all_buttons if "крипто" in btn.text.lower()), None)
        assert crypto_btn is not None
        assert "⬜" in crypto_btn.text

    @patch("telegram_bot.keyboards.cache_manager")
    def test_preferred_topics_show_checkmark(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {
            "preferred_topics": ["крипто", "технологии"],
            "blocked_topics": [],
            "min_score": 5,
        }
        kb = build_settings_keyboard("123456")

        # Находим кнопку крипто — должна быть с ✅
        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        crypto_btn = next((btn for btn in all_buttons if "крипто" in btn.text.lower()), None)
        assert crypto_btn is not None
        assert "✅" in crypto_btn.text

    @patch("telegram_bot.keyboards.cache_manager")
    def test_blocked_topics_show_block_icon(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {
            "preferred_topics": [],
            "blocked_topics": ["спорт"],
            "min_score": 3,
        }
        kb = build_settings_keyboard("123456")

        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        sport_btn = next((btn for btn in all_buttons if "спорт" in btn.text.lower()), None)
        assert sport_btn is not None
        assert "🚫" in sport_btn.text

    @patch("telegram_bot.keyboards.cache_manager")
    def test_min_score_displayed(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {
            "preferred_topics": [],
            "blocked_topics": [],
            "min_score": 7,
        }
        kb = build_settings_keyboard("123456")

        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        score_btn = next((btn for btn in all_buttons if "Минимальный балл" in btn.text), None)
        assert score_btn is not None
        assert "7" in score_btn.text

    @patch("telegram_bot.keyboards.cache_manager")
    def test_has_back_button(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {}
        kb = build_settings_keyboard("123456")

        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert "Назад" in last_row[0].text
        assert last_row[0].callback_data == "start_menu"

    @patch("telegram_bot.keyboards.cache_manager")
    def test_topic_toggle_callbacks(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {}
        kb = build_settings_keyboard("123456")

        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        # Проверяем callback_data для тем подписки
        for label, topic in _PRESET_TOPICS:
            btn = next((b for b in all_buttons if topic in b.callback_data), None)
            assert btn is not None, f"Кнопка для темы {topic} не найдена"
            assert btn.callback_data == f"topic_toggle:{topic}"

    @patch("telegram_bot.keyboards.cache_manager")
    def test_block_toggle_callbacks(self, mock_cache):
        mock_cache.get_user_prefs.return_value = {}
        kb = build_settings_keyboard("123456")

        all_buttons = []
        for row in kb.inline_keyboard:
            all_buttons.extend(row)

        for label, topic in _PRESET_BLOCKED:
            btn = next((b for b in all_buttons if f"block_toggle:{topic}" == b.callback_data), None)
            assert btn is not None, f"Кнопка блокировки {topic} не найдена"
            assert btn.callback_data == f"block_toggle:{topic}"


class TestBuildMinscoreKeyboard:
    """Тесты для build_minscore_keyboard."""

    def test_returns_inline_keyboard_markup(self):
        kb = build_minscore_keyboard(5)
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_10_score_buttons(self):
        kb = build_minscore_keyboard(5)
        # 10 кнопок баллов + кнопка "Назад"
        score_buttons = []
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("minscore_set:"):
                    score_buttons.append(btn)
        assert len(score_buttons) == 10

    def test_current_score_has_filled_icon(self):
        kb = build_minscore_keyboard(5)
        score_btn = None
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data == "minscore_set:5":
                    score_btn = btn
                    break
        assert score_btn is not None
        assert "●" in score_btn.text

    def test_other_scores_have_empty_icon(self):
        kb = build_minscore_keyboard(5)
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("minscore_set:"):
                    if btn.callback_data != "minscore_set:5":
                        assert "○" in btn.text

    def test_score_callbacks_correct(self):
        kb = build_minscore_keyboard(1)
        for score in range(1, 11):
            btn = None
            for row in kb.inline_keyboard:
                for b in row:
                    if b.callback_data == f"minscore_set:{score}":
                        btn = b
                        break
            assert btn is not None, f"Кнопка для балла {score} не найдена"
            assert str(score) in btn.text

    def test_has_back_button(self):
        kb = build_minscore_keyboard(3)
        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert "Назад" in last_row[0].text
        assert last_row[0].callback_data == "settings_menu"

    def test_buttons_in_rows_of_5(self):
        kb = build_minscore_keyboard(1)
        # Первые 2 ряда должны содержать по 5 кнопок (score buttons)
        score_rows = [
            row
            for row in kb.inline_keyboard
            if all(b.callback_data and b.callback_data.startswith("minscore_set:") for b in row)
        ]
        assert len(score_rows) == 2
        assert len(score_rows[0]) == 5
        assert len(score_rows[1]) == 5
