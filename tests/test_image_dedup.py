"""
Tests for image deduplication and relevance improvements.
"""

import pytest

from utils.image_search import _is_rss_placeholder


class TestImageDedup:
    """Тесты дедупликации изображений."""

    def test_rss_placeholder_logo(self):
        assert _is_rss_placeholder("https://example.com/logo.jpg") is True

    def test_rss_placeholder_generic(self):
        assert _is_rss_placeholder("https://example.com/generic.png") is True

    def test_rss_placeholder_cover(self):
        assert _is_rss_placeholder("https://cdn.sanity.io/article-covers/foo.jpg") is True

    def test_rss_placeholder_sharing(self):
        assert _is_rss_placeholder("https://ria.ru/sharing/article/123.jpg") is True

    def test_rss_placeholder_flagcdn(self):
        assert _is_rss_placeholder("https://flagcdn.com/w320/ru.png") is True

    def test_rss_real_photo_not_placeholder(self):
        assert (
            _is_rss_placeholder("https://mf.b37mrtl.ru/russian/images/2026.06/article/abc.jpg")
            is False
        )

    def test_rss_empty_url_is_placeholder(self):
        assert _is_rss_placeholder("") is True

    def test_rss_normal_photo(self):
        assert _is_rss_placeholder("https://example.com/news/photo.jpg") is False
