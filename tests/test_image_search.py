"""
Tests for image_search module (SearXNG integration).
"""

import asyncio
from unittest.mock import patch

import pytest

from utils.image_search import find_news_image


class TestFindNewsImage:
    @patch("utils.image_search.searxng_find_best_image")
    @patch("utils.image_search.image_judge")
    def test_returns_searxng_result_when_available(self, mock_judge, mock_searxng):
        import asyncio

        mock_searxng.return_value = "https://example.com/news-photo.jpg"

        async def mock_judge_result(*args, **kwargs):
            return type(
                "JudgeResult",
                (),
                {
                    "selected_url": "https://example.com/news-photo.jpg",
                    "score": 60,
                    "reason": "OK",
                    "cost_usd": 0.0,
                },
            )()

        mock_judge.judge = mock_judge_result
        result = asyncio.run(find_news_image("Test title", "RIA", "Summary"))
        assert result == "https://example.com/news-photo.jpg"

    @patch("utils.image_search.searxng_find_best_image")
    @patch("utils.image_search.image_judge")
    def test_returns_fallback_when_searxng_fails(self, mock_judge, mock_searxng):
        mock_searxng.return_value = None
        result = asyncio.run(find_news_image("Test title", "RIA", "Summary"))
        assert result is None

    @patch("utils.image_search.searxng_find_best_image")
    @patch("utils.image_search.image_judge")
    def test_returns_fallback_for_cnbc(self, mock_judge, mock_searxng):
        mock_searxng.return_value = None
        result = asyncio.run(find_news_image("Test title", "CNBC", "Summary"))
        assert result is None

    @patch("utils.image_search.searxng_find_best_image")
    @patch("utils.image_search.image_judge")
    def test_returns_none_for_unknown_source(self, mock_judge, mock_searxng):
        mock_searxng.return_value = None
        result = asyncio.run(find_news_image("Test title", "UnknownBlog", "Summary"))
        assert result is None

    @patch("utils.image_search.searxng_find_best_image")
    @patch("utils.image_search.image_judge")
    def test_searxng_called_with_title_and_summary(self, mock_judge, mock_searxng):
        import asyncio

        mock_searxng.return_value = "https://example.com/photo.jpg"

        async def mock_judge_result(*args, **kwargs):
            return type(
                "JudgeResult",
                (),
                {
                    "selected_url": "https://example.com/photo.jpg",
                    "score": 60,
                    "reason": "OK",
                    "cost_usd": 0.0,
                },
            )()

        mock_judge.judge = mock_judge_result
        asyncio.run(find_news_image("Trump meets Putin", "RIA", "Important news"))
        mock_searxng.assert_called_with("Trump meets Putin", "Important news", max_results=5)
