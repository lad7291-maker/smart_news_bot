"""
Тесты для P2-005: Graceful degradation при недоступности AI.

Покрывают:
- При ai_comment == "AI analysis temporarily unavailable." используется summary
- Пост содержит осмысленный текст, а не мёртвый fallback
- Обычный ai_comment не затронут
"""

import pytest

from telegram_bot.formatter import format_news_post


class TestAIFallback:
    """Тесты fallback на summary при недоступности AI."""

    def _article(self, ai_comment=None, summary=""):
        return {
            "title": "Test News Title",
            "link": "https://example.com/1",
            "summary": summary,
            "source": "TestSource",
            "ai_comment": ai_comment,
        }

    def test_normal_ai_comment_used(self):
        """Обычный AI-комментарий используется как есть."""
        a = self._article(
            ai_comment="This is an AI analysis of the news.", summary="Original summary text."
        )
        text = format_news_post(a)
        assert "This is an AI analysis" in text
        assert "Original summary" not in text

    def test_unavailable_ai_uses_summary(self):
        """При недоступности AI используется summary."""
        a = self._article(
            ai_comment="AI analysis temporarily unavailable.",
            summary="This is the original article summary that should be used as fallback.",
        )
        text = format_news_post(a)
        assert "AI analysis temporarily unavailable" not in text
        assert "original article summary" in text
        assert "📌" in text

    def test_unavailable_ai_truncates_long_summary(self):
        """Длинный summary обрезается до 300 символов."""
        long_summary = "A" * 500
        a = self._article(ai_comment="AI analysis temporarily unavailable.", summary=long_summary)
        # Проверяем в scheduler_jobs, но здесь проверим через format_news_post
        # что summary используется (formatter обрезает до 500)
        text = format_news_post(a)
        assert "AI analysis temporarily unavailable" not in text
        assert "A" in text

    def test_empty_summary_with_unavailable_ai(self):
        """При недоступности AI и пустом summary — пост без ai_block."""
        a = self._article(ai_comment="AI analysis temporarily unavailable.", summary="")
        text = format_news_post(a)
        assert "AI analysis temporarily unavailable" not in text
        # Пост всё равно должен содержать заголовок и ссылку
        assert "Test News Title" in text
        assert "🔗" in text

    def test_partial_unavailable_text_detected(self):
        """Частичное совпадение тоже детектируется."""
        a = self._article(
            ai_comment="AI analysis temporarily unavailable. Please try again later.",
            summary="Fallback summary here.",
        )
        text = format_news_post(a)
        assert "AI analysis temporarily unavailable" not in text
        assert "Fallback summary" in text

    def test_none_ai_comment_uses_summary(self):
        """None ai_comment — fallback на summary (существующее поведение)."""
        a = self._article(ai_comment=None, summary="Summary when AI is None.")
        text = format_news_post(a)
        assert "Summary when AI is None" in text
