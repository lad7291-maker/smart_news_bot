"""Tests for CLIP-based image relevance scoring."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

# Disable mkldnn for tests (same as production workaround)
torch.backends.mkldnn.enabled = False

from utils.image_clip import (
    RELEVANCE_MODERATE,
    RELEVANCE_STRONG,
    RELEVANCE_WEAK,
    CLIPScoreResult,
    batch_score_images,
    score_image_relevance,
)


@pytest.fixture
def red_image():
    """Create a simple red test image."""
    return Image.new("RGB", (224, 224), color="red")


@pytest.fixture
def blue_image():
    """Create a simple blue test image."""
    return Image.new("RGB", (224, 224), color="blue")


@pytest.mark.asyncio
async def test_score_image_relevance_basic(red_image):
    """CLIP should score 'a red square' highly for a red image."""
    result = await score_image_relevance(red_image, "a red square")

    assert isinstance(result, CLIPScoreResult)
    assert result.score > 0.5  # Red square vs red image should be very high
    assert result.is_relevant is True
    assert result.label == "strong"


@pytest.mark.asyncio
async def test_score_image_relevance_low_relevance(red_image):
    """CLIP should score lower for unrelated text than matching text."""
    result_match = await score_image_relevance(red_image, "a red square")
    result_unrelated = await score_image_relevance(red_image, "deep ocean underwater photography")

    assert isinstance(result_unrelated, CLIPScoreResult)
    # Matching should score higher than unrelated
    assert result_match.score > result_unrelated.score
    # Unrelated should be below moderate threshold
    assert result_unrelated.score < RELEVANCE_MODERATE
    assert result_unrelated.is_relevant is False


@pytest.mark.asyncio
async def test_score_image_relevance_empty_title(red_image):
    """Empty title should return zero score."""
    result = await score_image_relevance(red_image, "")

    assert result.score == 0.0
    assert result.is_relevant is False
    assert result.label == "none"


@pytest.mark.asyncio
async def test_score_image_relevance_no_image():
    """No image should return zero score."""
    result = await score_image_relevance(None, "some title")

    assert result.score == 0.0
    assert result.is_relevant is False
    assert result.label == "none"


@pytest.mark.asyncio
async def test_batch_score_images(red_image, blue_image):
    """Batch scoring should work for multiple images."""
    images = [red_image, blue_image]
    titles = ["a red square", "a blue circle"]

    results = await batch_score_images(images, titles)

    assert len(results) == 2
    assert all(isinstance(r, CLIPScoreResult) for r in results)
    # First should score high for red
    assert results[0].score > RELEVANCE_MODERATE
    # Second should score high for blue
    assert results[1].score > RELEVANCE_MODERATE


@pytest.mark.asyncio
async def test_batch_score_images_mismatched_lengths(red_image):
    """Mismatched lengths should raise ValueError."""
    with pytest.raises(ValueError):
        await batch_score_images([red_image], ["title1", "title2"])


@pytest.mark.asyncio
async def test_batch_score_images_empty():
    """Empty lists should return empty results."""
    results = await batch_score_images([], [])
    assert results == []


@pytest.mark.asyncio
async def test_score_image_relevance_long_title(red_image):
    """Very long title should be truncated without error."""
    long_title = "news " * 100  # Way over 250 chars
    result = await score_image_relevance(red_image, long_title)

    assert isinstance(result, CLIPScoreResult)
    assert 0.0 <= result.score <= 1.0


@pytest.mark.asyncio
async def test_model_singleton():
    """Model should be loaded only once (singleton pattern)."""
    from utils.image_clip import _load_model

    model1, processor1, device1 = _load_model()
    model2, processor2, device2 = _load_model()

    assert model1 is model2
    assert processor1 is processor2
    assert device1 == device2
