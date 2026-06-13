"""
Tests for Pydantic Article model (P2-002).
"""

from datetime import datetime

import pytest

from models.article import Article


class TestArticleModel:
    def test_basic_creation(self):
        a = Article(title="Test", link="https://example.com")
        assert a.title == "Test"
        assert a.link == "https://example.com"
        assert a.source == "News"
        assert a.type == "rss"
        assert a.score is None

    def test_validation_empty_title(self):
        with pytest.raises(Exception):
            Article(title="", link="https://example.com")

    def test_validation_whitespace_title(self):
        with pytest.raises(Exception):
            Article(title="   ", link="https://example.com")

    def test_validation_bad_link(self):
        with pytest.raises(Exception):
            Article(title="T", link="not-a-url")

    def test_validation_score_range(self):
        with pytest.raises(Exception):
            Article(title="T", link="https://x.com", score=15)
        with pytest.raises(Exception):
            Article(title="T", link="https://x.com", score=0)

    def test_from_dict(self):
        data = {
            "title": "From Dict",
            "link": "https://example.com",
            "summary": "Summary text",
            "source": "CoinDesk",
            "score": 7,
            "published": datetime(2026, 5, 31, 12, 0, 0),
        }
        a = Article.from_dict(data)
        assert a.title == "From Dict"
        assert a.score == 7
        assert a.source_tag == "CoinDesk"  # synced from source

    def test_from_dict_string_published(self):
        a = Article.from_dict(
            {
                "title": "T",
                "link": "https://x.com",
                "published": "2026-05-31T12:00:00",
            }
        )
        assert a.published.year == 2026

    def test_to_dict_roundtrip(self):
        a = Article(
            title="Roundtrip",
            link="https://example.com",
            summary="S",
            source="Test",
            score=5,
        )
        d = a.to_dict()
        assert d["title"] == "Roundtrip"
        assert d["link"] == "https://example.com"
        assert d["score"] == 5

    def test_dict_like_get(self):
        a = Article(title="T", link="https://x.com", score=5)
        assert a.get("title") == "T"
        assert a.get("score") == 5
        assert a.get("missing", "default") == "default"
        assert a.get("missing") is None

    def test_dict_like_getitem(self):
        a = Article(title="T", link="https://x.com")
        assert a["title"] == "T"
        assert a["link"] == "https://x.com"

    def test_dict_like_setitem(self):
        a = Article(title="T", link="https://x.com")
        a["score"] = 8
        a["ai_comment"] = "Test"
        assert a.score == 8
        assert a.ai_comment == "Test"

    def test_level_property(self):
        assert Article(title="T", link="https://x.com", score=10).level == "red"
        assert Article(title="T", link="https://x.com", score=8).level == "orange"
        assert Article(title="T", link="https://x.com", score=5).level == "yellow"
        assert Article(title="T", link="https://x.com").level == "unknown"

    def test_has_image_property(self):
        a = Article(title="T", link="https://x.com")
        assert not a.has_image
        a["image_url"] = "https://img.com/1.jpg"
        assert a.has_image

    def test_display_title_property(self):
        a = Article(title="A" * 200, link="https://x.com")
        assert len(a.display_title) == 120

    @pytest.mark.asyncio
    async def test_from_rss_entry(self):
        class MockEntry:
            def get(self, key, default=""):
                return {
                    "title": "RSS Title",
                    "link": "https://rss.com",
                    "summary": "RSS Summary",
                }.get(key, default)

        entry = MockEntry()
        entry.published_parsed = (2026, 5, 31, 12, 0, 0, 0, 0, 0)
        a = await Article.from_rss_entry(entry, "TestSource")
        assert a.title == "RSS Title"
        assert a.link == "https://rss.com"
        assert a.source == "TestSource"
        assert a.published.year == 2026

    def test_source_tag_sync(self):
        a = Article(title="T", link="https://x.com", source="CoinDesk")
        assert a.source_tag == "CoinDesk"

        a2 = Article(title="T", link="https://x.com", source="CoinDesk", source_tag="Custom")
        assert a2.source_tag == "Custom"

    def test_extra_fields_allowed(self):
        """Pydantic extra='allow' позволяет добавлять произвольные поля."""
        a = Article(title="T", link="https://x.com")
        a["custom_field"] = "custom_value"
        assert a.custom_field == "custom_value"
