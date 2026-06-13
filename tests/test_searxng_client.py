"""
Tests for SearXNG client.
P1-002: Переписаны на async + httpx.AsyncClient моки.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.searxng_client import _build_query, _score_image_result, find_best_image, search_images


class TestBuildQuery:
    def test_short_query(self):
        q = _build_query("Trump meets Putin", "US President met Russian leader in Moscow")
        assert "trump" in q.lower() or "putin" in q.lower()
        assert len(q) <= 100

    def test_adds_news_suffix(self):
        q = _build_query("Trump meets Netanyahu", "Diplomatic summit")
        assert q.endswith(" news")


class TestScoreImageResult:
    def test_good_image_scores_high(self):
        result = {
            "img_src": "https://example.com/trump-photo.jpg",
            "resolution": "800x600",
        }
        score = _score_image_result(result, {"trump"})
        assert score > 0

    def test_bad_pattern_rejects(self):
        result = {"img_src": "https://example.com/logo.png"}
        score = _score_image_result(result, set())
        assert score == -100

    def test_no_url_rejects(self):
        result = {"title": "No image"}
        score = _score_image_result(result, set())
        assert score == -100


class TestSearchImages:
    @pytest.mark.asyncio
    @patch("utils.searxng_client.httpx.AsyncClient")
    async def test_successful_search(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={
                "results": [
                    {"img_src": "https://example.com/1.jpg", "title": "Photo 1"},
                    {"img_src": "https://example.com/2.jpg", "title": "Photo 2"},
                ]
            }
        )

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await search_images("test query")
        assert len(results) == 2
        assert results[0]["img_src"] == "https://example.com/1.jpg"

    @pytest.mark.asyncio
    @patch("utils.searxng_client.httpx.AsyncClient")
    async def test_connection_error_returns_empty(self, mock_client_cls):
        import httpx

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await search_images("test query")
        assert results == []

    @pytest.mark.asyncio
    @patch("utils.searxng_client.httpx.AsyncClient")
    async def test_timeout_returns_empty(self, mock_client_cls):
        import httpx

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await search_images("test query")
        assert results == []


class TestFindBestImage:
    @pytest.mark.asyncio
    @patch("utils.searxng_client.search_images")
    async def test_finds_best_image(self, mock_search):
        # Результат должен быть достаточно релевантным для порога 50
        mock_search.return_value = [
            {
                "img_src": "https://example.com/trump-speech-president.jpg",
                "title": "Trump speech president",
            },
            {"img_src": "https://example.com/logo.png", "title": "Logo"},
        ]
        result = await find_best_image("Trump speech", "President Trump addressed the nation")
        assert result == "https://example.com/trump-speech-president.jpg"

    @pytest.mark.asyncio
    @patch("utils.searxng_client.search_images")
    async def test_no_results_returns_none(self, mock_search):
        mock_search.return_value = []
        result = await find_best_image("Something obscure", "No images available")
        assert result is None

    @pytest.mark.asyncio
    @patch("utils.searxng_client.search_images")
    async def test_all_filtered_returns_none(self, mock_search):
        mock_search.return_value = [
            {"img_src": "https://example.com/logo.png"},
            {"img_src": "https://example.com/favicon.ico"},
        ]
        result = await find_best_image("Test", "Test summary")
        assert result is None
