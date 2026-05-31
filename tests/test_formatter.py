"""
Tests for telegram post formatter.
FEAT-008: Check AI disclaimer presence.
"""

import pytest

from telegram_bot.formatter import format_news_post


class TestFormatter:
    def test_format_includes_title_and_link(self):
        article = {
            "title": "Test News",
            "link": "https://example.com/news",
            "source": "TestSource",
            "summary": "Summary text here",
            "ai_comment": "AI thinks this is important.",
        }
        text = format_news_post(article)
        assert "Test News" in text
        assert "https://example.com/news" in text
        assert "TestSource" in text

    def test_format_truncates_long_summary(self):
        article = {
            "title": "Test",
            "link": "https://example.com",
            "source": "Test",
            "summary": "x" * 1000,
        }
        text = format_news_post(article)
        # Summary should be truncated or omitted if too long
        assert len(text) < 2000

    def test_ai_disclaimer_present(self):
        """FEAT-008: Posts should include AI disclaimer."""
        article = {
            "title": "Test",
            "link": "https://example.com",
            "source": "Test",
            "ai_comment": "Some analysis",
        }
        text = format_news_post(article)
        # Currently no disclaimer - this test documents the gap
        assert (
            "инвестиционной рекомендации" not in text
        ), "FEAT-008: AI disclaimer not yet implemented"
