"""
Tests for image_processor module.
"""

import asyncio
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from utils.image_processor import (
    ImageCheckResult,
    add_watermark,
    check_image_freshness,
    crop_to_aspect,
    generate_alt_text,
    image_to_bytes,
    process_image_for_telegram,
    resize_if_needed,
)


class TestCheckImageFreshness:
    @patch("utils.image_processor.httpx.AsyncClient")
    def test_accessible_image(self, mock_client_class):
        async def _run():
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.headers = {
                "content-type": "image/jpeg",
                "content-length": "12345",
                "last-modified": "Wed, 21 Oct 2025 07:28:00 GMT",
            }
            mock_client = AsyncMock()
            mock_client.head.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await check_image_freshness("https://example.com/photo.jpg")
            assert result.is_accessible is True
            assert result.is_fresh is True
            assert result.content_type == "image/jpeg"

        asyncio.run(_run())

    @patch("utils.image_processor.httpx.AsyncClient")
    def test_forbidden_image(self, mock_client_class):
        async def _run():
            mock_resp_head = AsyncMock()
            mock_resp_head.status_code = 403
            mock_resp_get = AsyncMock()
            mock_resp_get.status_code = 200
            mock_resp_get.headers = {"content-type": "image/jpeg"}
            mock_resp_get.content = b"fake_image_data"

            mock_client = AsyncMock()
            mock_client.head.return_value = mock_resp_head
            mock_client.get.return_value = mock_resp_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await check_image_freshness("https://example.com/photo.jpg")
            assert result.is_accessible is True

        asyncio.run(_run())

    @patch("utils.image_processor.httpx.AsyncClient")
    def test_old_image(self, mock_client_class):
        async def _run():
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.headers = {
                "content-type": "image/jpeg",
                "last-modified": "Wed, 21 Oct 2020 07:28:00 GMT",
            }
            mock_client = AsyncMock()
            mock_client.head.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await check_image_freshness("https://example.com/photo.jpg")
            assert result.is_accessible is True
            assert result.is_fresh is False

        asyncio.run(_run())


class TestCropToAspect:
    def test_wide_image(self):
        img = Image.new("RGB", (2000, 1000), color="red")
        result = crop_to_aspect(img, 16 / 9)
        assert result.size[0] / result.size[1] == pytest.approx(16 / 9, abs=0.1)

    def test_tall_image(self):
        img = Image.new("RGB", (1000, 2000), color="blue")
        result = crop_to_aspect(img, 16 / 9)
        assert result.size[0] / result.size[1] == pytest.approx(16 / 9, abs=0.1)

    def test_already_correct_aspect(self):
        img = Image.new("RGB", (1600, 900), color="green")
        result = crop_to_aspect(img, 16 / 9)
        assert result.size == (1600, 900)


class TestResizeIfNeeded:
    def test_no_resize_needed(self):
        img = Image.new("RGB", (800, 600))
        result = resize_if_needed(img, max_width=1920, max_height=1080)
        assert result.size == (800, 600)

    def test_resize_needed(self):
        img = Image.new("RGB", (4000, 2000))
        result = resize_if_needed(img, max_width=1920, max_height=1080)
        assert result.size[0] <= 1920
        assert result.size[1] <= 1080


class TestAddWatermark:
    def test_watermark_added(self):
        img = Image.new("RGB", (1000, 600), color="white")
        result = add_watermark(img, text="TEST")
        assert result.mode == "RGB"
        assert result.size == (1000, 600)


class TestImageToBytes:
    def test_jpeg_output(self):
        img = Image.new("RGB", (100, 100), color="red")
        data = image_to_bytes(img, format="JPEG")
        assert isinstance(data, bytes)
        assert len(data) > 0
        # Проверяем, что это валидное JPEG
        assert data[:2] == b"\xff\xd8"


class TestGenerateAltText:
    def test_with_title(self):
        result = asyncio.run(generate_alt_text("Trump meets Putin in Geneva"))
        assert "Trump meets Putin in Geneva" in result

    def test_empty_title(self):
        result = asyncio.run(generate_alt_text(""))
        assert result == "Новостное изображение"

    def test_long_title_truncated(self):
        long_title = "A" * 300
        result = asyncio.run(generate_alt_text(long_title))
        assert len(result) <= 230  # "Изображение к новости: " (23) + 197 + "..." (3) = 223


class TestProcessImageForTelegram:
    @patch("utils.image_processor.check_image_freshness")
    @patch("utils.image_processor.download_image")
    def test_successful_processing(self, mock_download, mock_check):
        async def _run():
            mock_check.return_value = ImageCheckResult(
                url="https://example.com/photo.jpg",
                is_accessible=True,
                is_fresh=True,
                content_type="image/jpeg",
                last_modified=None,
                size_bytes=12345,
                width=None,
                height=None,
            )
            mock_download.return_value = Image.new("RGB", (1600, 900), color="blue")

            result = await process_image_for_telegram(
                "https://example.com/photo.jpg",
                article_title="Test",
                source="searxng",
            )
            assert result is not None
            assert isinstance(result, bytes)

        asyncio.run(_run())

    @patch("utils.image_processor.check_image_freshness")
    def test_inaccessible_image(self, mock_check):
        async def _run():
            # Очищаем кэш перед тестом
            import os

            from utils.image_processor import IMAGE_CACHE_DIR, _get_cache_path

            cache_path = _get_cache_path("https://example.com/photo.jpg")
            if os.path.exists(cache_path):
                os.remove(cache_path)

            mock_check.return_value = ImageCheckResult(
                url="https://example.com/photo.jpg",
                is_accessible=False,
                is_fresh=False,
                content_type=None,
                last_modified=None,
                size_bytes=None,
                width=None,
                height=None,
                error="404",
            )

            result = await process_image_for_telegram("https://example.com/photo.jpg")
            assert result is None

        asyncio.run(_run())
