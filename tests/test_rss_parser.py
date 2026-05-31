"""
Tests for RSS parser.
FEAT-011: RSS parsing logic.
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from parsers.rss_parser import RSSParser


class TestRSSParser:
    def test_extract_published_date_with_published_parsed(self):
        parser = RSSParser()
        entry = MagicMock()
        entry.published_parsed = (2026, 5, 31, 12, 0, 0, 0, 0, 0)
        entry.updated_parsed = None
        entry.created_parsed = None
        result = parser._extract_published_date(entry)
        assert result.year == 2026
        assert result.month == 5
        assert result.day == 31

    def test_extract_published_date_fallback_to_now(self):
        parser = RSSParser()
        entry = MagicMock()
        entry.published_parsed = None
        entry.updated_parsed = None
        entry.created_parsed = None
        result = parser._extract_published_date(entry)
        assert isinstance(result, datetime)
        assert (datetime.now() - result).total_seconds() < 5

    def test_build_article_structure(self):
        parser = RSSParser()
        entry = MagicMock()
        entry.get = lambda key, default="": {
            "title": "Test Title",
            "link": "https://example.com",
            "summary": "Test summary",
            "description": "Test desc",
        }.get(key, default)
        article = parser._build_article(entry, "TestSource", datetime.now())
        assert article["title"] == "Test Title"
        assert article["source"] == "TestSource"
        assert article["type"] == "rss"

    def test_clean_text_removes_html(self):
        parser = RSSParser()
        text = "<p>Hello <b>world</b></p>"
        result = parser._clean_text(text)
        assert "<p>" not in result
        assert "Hello" in result
        assert "world" in result
