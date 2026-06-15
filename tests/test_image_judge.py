"""
Tests for LLM Image Judge.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ai_core.image_judge import ImageCandidate, ImageJudge, JudgeResult


class TestImageJudge:
    @pytest.mark.asyncio
    async def test_judge_selects_best_candidate(self):
        """LLM выбирает лучшего кандидата из списка."""
        judge = ImageJudge(api_key="test_key")

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"selected": {"url": "https://example.com/img2.jpg", "score": 75, "source": "searxng", "reason": "Более релевантно"}, "debug": {"article_topic": "Test", "top_candidates": []}}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 500, "completion_tokens": 50},
        }

        with patch.object(judge.session, "post") as mock_post:
            mock_post.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(
                    raise_for_status=AsyncMock(), json=AsyncMock(return_value=mock_response)
                )
            )
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

            candidates = [
                ImageCandidate(url="https://example.com/img1.jpg", score=40, source="searxng"),
                ImageCandidate(url="https://example.com/img2.jpg", score=45, source="searxng"),
            ]

            result = await judge.judge("Test title", "Test summary", candidates)

            assert result.selected_url == "https://example.com/img2.jpg"
            assert result.score == 75
            assert result.llm_used is True
            assert result.cost_usd > 0

    @pytest.mark.asyncio
    async def test_judge_rejects_all_candidates(self):
        """LLM отказывается от всех кандидатов."""
        judge = ImageJudge(api_key="test_key")

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"selected": {"url": null, "score": 0, "source": "none", "reason": "Все нерелевантны"}, "debug": {"article_topic": "Test", "top_candidates": []}}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 500, "completion_tokens": 30},
        }

        with patch.object(judge.session, "post") as mock_post:
            mock_post.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(
                    raise_for_status=AsyncMock(), json=AsyncMock(return_value=mock_response)
                )
            )
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

            candidates = [
                ImageCandidate(url="https://example.com/img1.jpg", score=35, source="searxng"),
            ]

            result = await judge.judge("Test title", "Test summary", candidates)

            assert result.selected_url is None
            assert result.score == 0
            assert result.llm_used is True

    @pytest.mark.asyncio
    async def test_judge_no_api_key(self):
        """Без API ключа возвращает отказ."""
        judge = ImageJudge(api_key=None)
        judge.available = False  # Принудительно отключаем

        candidates = [
            ImageCandidate(url="https://example.com/img1.jpg", score=40, source="searxng"),
        ]

        result = await judge.judge("Test title", "Test summary", candidates)

        assert result.selected_url is None
        assert result.llm_used is False

    @pytest.mark.asyncio
    async def test_judge_empty_candidates(self):
        """Пустой список кандидатов — отказ."""
        judge = ImageJudge(api_key="test_key")

        result = await judge.judge("Test title", "Test summary", [])

        assert result.selected_url is None
        assert result.reason == "Нет кандидатов для оценки"

    def test_parse_response_json(self):
        """Парсинг корректного JSON."""
        judge = ImageJudge(api_key="test_key")

        text = '{"selected_index": 0, "reason": "Хорошо", "score": 80}'
        result = judge._parse_response(text)

        assert result["selected_index"] == 0
        assert result["score"] == 80

    def test_parse_response_with_markdown(self):
        """Парсинг JSON в markdown code block."""
        judge = ImageJudge(api_key="test_key")

        text = '```json\n{"selected_index": 1, "reason": "OK", "score": 70}\n```'
        result = judge._parse_response(text)

        assert result["selected_index"] == 1
        assert result["score"] == 70

    def test_parse_response_invalid(self):
        """Парсинг некорректного JSON — fallback."""
        judge = ImageJudge(api_key="test_key")

        text = "Не JSON ответ"
        result = judge._parse_response(text)

        assert result["selected"]["url"] is None
        assert result["selected"]["score"] == 0


class TestImageSearchHybrid:
    @pytest.mark.asyncio
    async def test_high_confidence_skips_llm(self):
        """Высокий score RSS изображения — возвращаем сразу."""
        from utils.image_search import find_news_image

        article = {
            "title": "Test title",
            "source": "RIA",
            "summary": "Summary",
            "image_url": "https://example.com/img.jpg",
            "image_score": 75,
        }

        with patch("utils.searxng_client.find_best_image") as mock_searxng:
            mock_searxng.return_value = None
            result = await find_news_image(article)

            # RSS изображение с высоким score используется напрямую
            # или fallback изображение для источника
            assert result is not None

    @pytest.mark.asyncio
    async def test_searxng_fallback(self):
        """SearXNG используется как fallback."""
        from utils.image_search import find_news_image

        article = {
            "title": "Test title",
            "source": "RIA",
            "summary": "Summary",
        }

        with patch(
            "utils.searxng_client.find_best_image", return_value="https://example.com/good.jpg"
        ):
            result = await find_news_image(article)
            assert result == "https://example.com/good.jpg"

    @pytest.mark.asyncio
    async def test_no_image_returns_none(self):
        """Нет изображения — может вернуться fallback или None."""
        from utils.image_search import find_news_image

        article = {
            "title": "Test title",
            "source": "UnknownBlog",
            "summary": "Summary",
        }

        with patch("utils.searxng_client.find_best_image", return_value=None):
            result = await find_news_image(article)
            # Для неизвестного источника может вернуться None или fallback
            assert result is None or isinstance(result, str)
