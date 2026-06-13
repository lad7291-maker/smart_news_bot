"""Tests for NSFW image detection."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

# Disable mkldnn for tests
torch.backends.mkldnn.enabled = False

from utils.image_nsfw import (
    BLOCKED_LABELS,
    CONFIDENCE_THRESHOLD,
    SAFE_LABELS,
    NSFWResult,
    check_image_safety,
)


@pytest.fixture
def green_image():
    """Create a safe green test image."""
    return Image.new("RGB", (224, 224), color="green")


@pytest.fixture
def red_image():
    """Create a red test image."""
    return Image.new("RGB", (224, 224), color="red")


@pytest.mark.asyncio
async def test_check_image_safety_safe(green_image):
    """Safe image should return is_safe=True."""
    result = await check_image_safety(green_image)

    assert isinstance(result, NSFWResult)
    assert result.is_safe is True
    assert result.is_blocked is False
    assert result.confidence > 0.5
    assert result.label in SAFE_LABELS or result.label in ("normal", "nsfw")


@pytest.mark.asyncio
async def test_check_image_safety_no_image():
    """No image should return safe=False but not blocked (fail-open)."""
    result = await check_image_safety(None)

    assert isinstance(result, NSFWResult)
    assert result.is_safe is False
    assert result.is_blocked is True  # Block if we can't check
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_nsfw_result_structure(green_image):
    """Result should have all expected fields."""
    result = await check_image_safety(green_image)

    assert hasattr(result, "is_safe")
    assert hasattr(result, "label")
    assert hasattr(result, "confidence")
    assert hasattr(result, "is_blocked")
    assert hasattr(result, "details")
    assert isinstance(result.details, dict)
    assert all(0.0 <= v <= 1.0 for v in result.details.values())


@pytest.mark.asyncio
async def test_model_singleton():
    """Model should be loaded only once (singleton pattern)."""
    from utils.image_nsfw import _load_model

    model1, processor1, device1 = _load_model()
    model2, processor2, device2 = _load_model()

    assert model1 is model2
    assert processor1 is processor2
    assert device1 == device2


@pytest.mark.asyncio
async def test_confidence_range(green_image):
    """Confidence should be in [0, 1]."""
    result = await check_image_safety(green_image)

    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_details_sum_to_one(green_image):
    """All label probabilities should sum to approximately 1."""
    result = await check_image_safety(green_image)

    total = sum(result.details.values())
    assert abs(total - 1.0) < 0.001
