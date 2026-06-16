"""
Tests for smart summary/AI switching in formatter.
"""

import pytest

from telegram_bot.formatter import _ai_covers_summary


class TestAICoversSummary:
    """Тесты умного переключения summary ↔ AI comment."""

    def test_ai_empty_uses_summary(self):
        """Если AI пустой — summary должен показываться."""
        assert _ai_covers_summary("", "Сенат заблокировал резолюцию") is False

    def test_ai_short_uses_summary(self):
        """Если AI короткий (< 30 символов) — summary должен показываться."""
        assert _ai_covers_summary("Кратко: провал.", "Сенат заблокировал резолюцию") is False

    def test_ai_covers_summary_no_dup(self):
        """AI не покрывает summary — нужно показывать оба."""
        ai = "Интересный поворот в политике."
        summary = "Сенат заблокировал резолюцию о военных полномочиях Трампа"
        assert _ai_covers_summary(ai, summary) is False

    def test_ai_covers_summary_yes_dup(self):
        """AI покрывает summary — показываем только AI."""
        ai = "Сенат США не поддержал резолюцию, которая ограничила бы военные полномочия Трампа против Ирана."
        summary = "Сенат заблокировал резолюцию о военных полномочиях Трампа"
        assert _ai_covers_summary(ai, summary) is True

    def test_ai_covers_with_keywords(self):
        """AI содержит ключевые слова из summary — считаем покрытым."""
        ai = "Сенат проголосовал против ограничения полномочий президента."
        summary = "Сенат заблокировал резолюцию о военных полномочиях Трампа"
        assert _ai_covers_summary(ai, summary) is True

    def test_empty_summary_covered(self):
        """Пустой summary считается покрытым (нечего показывать)."""
        assert _ai_covers_summary("Хороший анализ ситуации с подробностями.", "") is True
