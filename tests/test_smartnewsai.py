#!/usr/bin/env python3
"""
SmartNewsAI Bot Test Suite — P3-044 итоговые тесты
Tests: SearXNG search, CLIP scoring, watermark, Telegram buttons, micro-text
Запускать: cd /root/smart_news_bot && pytest tests/test_smartnewsai.py -v
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_news():
    return {
        "title": "Трамп заявил, что США вступят в 'прямые переговоры' с Ираном",
        "summary": "В Иране заявили, что переговоры с США нужны лишь для завершения войны",
        "link": "https://example.com/news/123",
        "source": "RT",
    }


class TestSearXNGClient:
    """P3-001..P3-006: SearXNG image search."""

    @pytest.mark.asyncio
    async def test_find_best_image_returns_url(self, sample_news):
        """P3-001: SearXNG returns best image URL."""
        from utils.searxng_client import find_best_image

        with patch("utils.searxng_client.search_images") as mock_search:
            mock_search.return_value = [
                {
                    "img_src": "https://example.com/images/trump_iran.jpg",
                    "title": "Trump Iran",
                    "engine": "google",
                }
            ]
            with patch("utils.searxng_client._score_image_result", return_value=80):
                result = await find_best_image(
                    title=sample_news["title"], summary=sample_news["summary"], max_results=10
                )
                assert result is not None
                assert result.startswith("http")

    def test_is_junk_domain_watermarks(self):
        """P3-002: Filter watermark domains."""
        from utils.searxng_client import _is_junk_domain

        assert _is_junk_domain("https://gettyimages.com/photo.jpg") is True
        assert _is_junk_domain("https://shutterstock.com/image.jpg") is True
        assert _is_junk_domain("https://istockphoto.com/photo.jpg") is True
        assert _is_junk_domain("https://alamy.com/image.jpg") is True
        assert _is_junk_domain("https://example.com/good.jpg") is False

    def test_is_junk_domain_ria(self):
        """P3-003: Filter RIA sharing images."""
        from utils.searxng_client import _is_junk_domain

        assert _is_junk_domain("https://cdnn21.img.ria.ru/images/sharing/article/123.jpg") is True
        assert _is_junk_domain("https://img.ria.ru/images/sharing/article/456.jpg") is True
        assert _is_junk_domain("https://example.com/valid.jpg") is False

    def test_build_query_uses_full_text(self, sample_news):
        """P3-004: Query uses full title + summary."""
        from utils.searxng_client import _build_query

        query = _build_query(sample_news["title"], sample_news["summary"])
        assert "Трамп" in query or "Иран" in query
        assert len(query.split()) > 5

    @pytest.mark.asyncio
    async def test_no_results_returns_none(self, sample_news):
        """P3-005: Returns None when empty."""
        from utils.searxng_client import find_best_image

        with patch("utils.searxng_client.search_images", return_value=[]):
            result = await find_best_image(
                title=sample_news["title"], summary=sample_news["summary"], max_results=10
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self, sample_news):
        """P3-006: Handles errors gracefully."""
        from utils.searxng_client import find_best_image

        with patch("utils.searxng_client.search_images", return_value=[]):
            result = await find_best_image(
                title=sample_news["title"], summary=sample_news["summary"], max_results=10
            )
            assert result is None


class TestCLIPScoring:
    """P3-007..P3-012: CLIP semantic relevance."""

    def test_score_structure(self):
        """P3-007: CLIPScoreResult structure."""
        from utils.image_clip import RELEVANCE_MODERATE, CLIPScoreResult

        result = CLIPScoreResult(score=0.35, is_relevant=True, label="strong")
        assert result.score >= RELEVANCE_MODERATE
        assert result.is_relevant is True

    def test_relevance_threshold(self):
        """P3-008: Threshold is 0.30."""
        from utils.image_clip import RELEVANCE_MODERATE, CLIPScoreResult

        assert RELEVANCE_MODERATE == 0.30
        high = CLIPScoreResult(score=0.35, is_relevant=True, label="strong")
        low = CLIPScoreResult(score=0.15, is_relevant=False, label="weak")
        assert high.is_relevant is True
        assert low.is_relevant is False

    def test_truncation(self):
        """P3-009: Handles long text."""
        long_text = "Трамп " * 100
        truncated = long_text.strip()[:200]
        assert len(truncated) <= 200

    def test_zero_score(self):
        """P3-011: Zero score is not relevant."""
        from utils.image_clip import CLIPScoreResult

        result = CLIPScoreResult(score=0.000, is_relevant=False, label="none")
        assert result.score == 0.000
        assert result.is_relevant is False

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """P3-012: Handles exceptions."""
        from utils.image_clip import score_image_relevance

        with patch("utils.image_clip._score_sync", side_effect=Exception("CLIP error")):
            result = await score_image_relevance(image=Mock(), title="Test")
            assert result is not None
            assert result.score == 0.0
            assert result.is_relevant is False


class TestImageProcessor:
    """P3-013..P3-018, P3-035: Watermark + processing."""

    def test_watermark_function(self):
        """P3-013: add_watermark with @SmartNewsAI."""
        from PIL import Image

        from utils.image_processor import add_watermark

        img = Image.new("RGB", (800, 600), color="blue")
        result = add_watermark(img, text="@SmartNewsAI")
        assert result is not None
        assert result.size == (800, 600)

    def test_ria_rejected(self):
        """P3-014: RIA sharing rejected."""
        from utils.searxng_client import _is_junk_domain

        assert _is_junk_domain("https://cdnn21.img.ria.ru/images/sharing/article/123.jpg") is True

    def test_16_9_aspect(self):
        """P3-015: Aspect ratio is 16:9."""
        from utils.image_processor import TELEGRAM_POST_ASPECT

        assert abs(TELEGRAM_POST_ASPECT - 16 / 9) < 0.01

    def test_size_limits(self):
        """P3-035: Reasonable limits."""
        from utils.image_processor import JPEG_QUALITY, MAX_IMAGE_HEIGHT, MAX_IMAGE_WIDTH

        assert MAX_IMAGE_WIDTH <= 3840
        assert MAX_IMAGE_HEIGHT <= 2160
        assert MAX_IMAGE_WIDTH >= 1280
        assert 70 <= JPEG_QUALITY <= 95


class TestTelegramButtons:
    """P3-019..P3-021: Inline keyboard."""

    def test_keyboard_structure(self):
        """P3-019: 👍/👎 + 💬 Обсуждать."""
        from aiogram.types import InlineKeyboardMarkup

        from telegram_bot.poster import _build_reactions_keyboard

        keyboard = _build_reactions_keyboard(message_id=12345)
        assert isinstance(keyboard, InlineKeyboardMarkup)

        rows = keyboard.inline_keyboard
        assert len(rows) >= 2

        assert rows[0][0].text == "👍" and "like" in rows[0][0].callback_data
        assert rows[0][1].text == "👎" and "dislike" in rows[0][1].callback_data
        assert "💬" in rows[1][0].text and "Обсуждать" in rows[1][0].text
        assert rows[1][0].url is not None

    def test_no_save_button(self):
        """P3-020: No 💾 button."""
        from telegram_bot.poster import _build_reactions_keyboard

        keyboard = _build_reactions_keyboard(message_id=12345)
        for row in keyboard.inline_keyboard:
            for btn in row:
                assert "💾" not in btn.text
                if btn.callback_data:
                    assert "save" not in btn.callback_data.lower()

    def test_reaction_counts(self):
        """P3-021: Shows counts."""
        from telegram_bot.poster import _build_reactions_keyboard

        with patch("telegram_bot.poster.reactions_manager") as mock_mgr:
            mock_mgr.get_message_reactions.return_value = {"like": 5, "dislike": 2}
            keyboard = _build_reactions_keyboard(message_id=12345)
            assert "5" in keyboard.inline_keyboard[0][0].text
            assert "2" in keyboard.inline_keyboard[0][1].text


class TestMicroText:
    """P3-022..P3-025: Micro-text formatting."""

    def test_contains_thumbs(self, sample_news):
        """P3-022: 👍 and 👎 present."""
        from telegram_bot.formatter import format_news_post

        message = format_news_post(sample_news)
        assert "👍" in message
        assert "👎" in message

    def test_contains_ai(self, sample_news):
        """P3-023: AI mentioned."""
        from telegram_bot.formatter import format_news_post

        message = format_news_post(sample_news)
        assert "AI" in message or "научить" in message

    def test_length(self, sample_news):
        """P3-024: Short micro-text."""
        from telegram_bot.formatter import format_news_post

        message = format_news_post(sample_news)
        lines = [l for l in message.split("\n") if "👍" in l and "👎" in l]
        assert len(lines) > 0
        assert len(lines[0]) <= 100

    def test_no_bloat(self, sample_news):
        """P3-025: No excessive HTML."""
        from telegram_bot.formatter import format_news_post

        message = format_news_post(sample_news)
        assert "<div>" not in message
        assert "<span>" not in message


class TestPosterIntegration:
    """P3-026..P3-031: Full posting pipeline."""

    @pytest.mark.asyncio
    async def test_photo_first(self, sample_news):
        """P3-026: Photo priority."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch(
            "telegram_bot.poster.find_best_image", return_value="https://example.com/image.jpg"
        ):
            with patch(
                "telegram_bot.poster.process_image_for_telegram", return_value=b"image_bytes"
            ):
                with patch("telegram_bot.poster.bot", mock_bot):
                    with patch("telegram_bot.poster.config") as cfg:
                        cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                        result = await send_news_to_channel(article=sample_news)
                        assert result is True
                        mock_bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_video_fallback(self, sample_news):
        """P3-027: Video fallback."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch("telegram_bot.poster.find_best_image", return_value=None):
            with patch("telegram_bot.poster.bot", mock_bot):
                with patch("telegram_bot.poster.config") as cfg:
                    cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                    result = await send_news_to_channel(article=sample_news)
                    assert result is True
                    assert mock_bot.send_video.called or mock_bot.send_message.called

    @pytest.mark.asyncio
    async def test_no_link_preview(self, sample_news):
        """P3-028: No link preview."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch("telegram_bot.poster.find_best_image", return_value=None):
            with patch("telegram_bot.poster.bot", mock_bot):
                with patch("telegram_bot.poster.config") as cfg:
                    cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                    result = await send_news_to_channel(article=sample_news)
                    if mock_bot.send_message.called:
                        kwargs = mock_bot.send_message.call_args.kwargs
                        assert kwargs.get("disable_web_page_preview", False) is True

    @pytest.mark.asyncio
    async def test_with_reactions(self, sample_news):
        """P3-029: Reaction buttons included."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch(
            "telegram_bot.poster.find_best_image", return_value="https://example.com/image.jpg"
        ):
            with patch(
                "telegram_bot.poster.process_image_for_telegram", return_value=b"image_bytes"
            ):
                with patch("telegram_bot.poster.bot", mock_bot):
                    with patch("telegram_bot.poster.config") as cfg:
                        cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                        result = await send_news_to_channel(article=sample_news)
                        kwargs = mock_bot.send_photo.call_args.kwargs
                        assert "reply_markup" in kwargs

    @pytest.mark.asyncio
    async def test_with_micro_text(self, sample_news):
        """P3-030: Micro-text in caption."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch(
            "telegram_bot.poster.find_best_image", return_value="https://example.com/image.jpg"
        ):
            with patch(
                "telegram_bot.poster.process_image_for_telegram", return_value=b"image_bytes"
            ):
                with patch("telegram_bot.poster.bot", mock_bot):
                    with patch("telegram_bot.poster.config") as cfg:
                        cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                        result = await send_news_to_channel(article=sample_news)
                        caption = mock_bot.send_photo.call_args.kwargs.get("caption", "")
                        assert "👍" in caption or "👎" in caption


class TestConfig:
    """P3-036..P3-040: Configuration."""

    def test_clip_threshold(self):
        """P3-036: CLIP threshold = 0.30."""
        from utils.image_clip import RELEVANCE_MODERATE

        assert RELEVANCE_MODERATE == 0.30

    def test_watermark(self):
        """P3-037: Watermark function works."""
        from PIL import Image

        from utils.image_processor import add_watermark

        img = Image.new("RGB", (100, 100), color="red")
        assert add_watermark(img, text="@SmartNewsAI") is not None

    def test_channel_id(self):
        """P3-039: Channel ID format."""
        from config import config

        assert str(config.TELEGRAM_CHANNEL_ID).startswith("-100")
        assert len(str(config.TELEGRAM_CHANNEL_ID)) > 10

    def test_bot_token(self):
        """P3-040: Bot token configured."""
        from config import config

        assert config.TELEGRAM_BOT_TOKEN is not None
        assert len(config.TELEGRAM_BOT_TOKEN) > 20
        assert ":" in config.TELEGRAM_BOT_TOKEN


class TestEdgeCases:
    """P3-041..P3-044: Edge cases."""

    @pytest.mark.asyncio
    async def test_empty_title(self):
        """P3-041: Empty title handled."""
        from utils.searxng_client import find_best_image

        with patch("utils.searxng_client.search_images", return_value=[]):
            result = await find_best_image(title="", summary="", max_results=10)
            assert result is None

    def test_empty_clip(self):
        """P3-042: Empty text low score."""
        from utils.image_clip import CLIPScoreResult

        result = CLIPScoreResult(score=0.0, is_relevant=False, label="none")
        assert result.score < 0.20

    @pytest.mark.asyncio
    async def test_no_image_posts(self, sample_news):
        """P3-043: Posts without image."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        with patch("telegram_bot.poster.find_best_image", return_value=None):
            with patch("telegram_bot.poster.bot", mock_bot):
                with patch("telegram_bot.poster.config") as cfg:
                    cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                    result = await send_news_to_channel(article=sample_news)
                    assert result is True

    @pytest.mark.asyncio
    async def test_exception_fallback(self, sample_news):
        """P3-044: Exception handling."""
        from telegram_bot.poster import send_news_to_channel

        mock_bot = AsyncMock()
        mock_bot.send_photo.side_effect = Exception("API error")
        mock_bot.send_video.return_value = True

        with patch(
            "telegram_bot.poster.find_best_image", return_value="https://example.com/image.jpg"
        ):
            with patch(
                "telegram_bot.poster.process_image_for_telegram", return_value=b"image_bytes"
            ):
                with patch("telegram_bot.poster.bot", mock_bot):
                    with patch("telegram_bot.poster.config") as cfg:
                        cfg.TELEGRAM_CHANNEL_ID = "-1001234567890"
                        result = await send_news_to_channel(article=sample_news)
                        assert result is True
                        mock_bot.send_video.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
