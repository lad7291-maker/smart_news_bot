"""
NSFW (Not Safe For Work) image detector.

Uses a lightweight open-source model based on CLIP embeddings + classification head.
The model "Falconsai/nsfw_image_detection" is a 86M-param vision transformer
fine-tuned specifically for NSFW detection. Runs locally, zero cost.

Categories:
- "normal": Safe content
- "nsfw": Adult / sexual content
- "hentai": Animated adult content
- "porn": Explicit content
- "sexy": Suggestive but not explicit

We treat "nsfw", "porn", "hentai" as BLOCKED.
"sexy" gets a warning but is allowed (many news photos have this label incorrectly).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification

# FIX: PyTorch 2.12 oneDNN bug на CPU — отключаем MKL-DNN
# https://github.com/pytorch/pytorch/issues/...
torch.backends.mkldnn.enabled = False

torch.set_num_threads(1)

logger = logging.getLogger(__name__)

# Lazy-loaded singletons
_nsfw_model: Optional[AutoModelForImageClassification] = None
_nsfw_processor: Optional[AutoImageProcessor] = None
_device: Optional[str] = None

MODEL_NAME = "Falconsai/nsfw_image_detection"

# Labels that result in immediate block
BLOCKED_LABELS = {"nsfw", "porn", "hentai"}
# Labels that trigger warning but are allowed
WARNING_LABELS = {"sexy"}
# Safe labels
SAFE_LABELS = {"normal"}

# Minimum confidence to take action
CONFIDENCE_THRESHOLD = 0.70


@dataclass
class NSFWResult:
    """Результат проверки на NSFW."""

    is_safe: bool
    label: str  # top predicted label
    confidence: float  # 0.0 - 1.0
    is_blocked: bool  # True if blocked by policy
    details: dict[str, float]  # all label scores


def _load_model() -> tuple[AutoModelForImageClassification, AutoImageProcessor, str]:
    """Lazy-load NSFW model and processor."""
    global _nsfw_model, _nsfw_processor, _device

    if _nsfw_model is None:
        logger.info("🔄 Loading NSFW detection model (%s)...", MODEL_NAME)
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _nsfw_processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
        _nsfw_model = AutoModelForImageClassification.from_pretrained(MODEL_NAME).to(_device).eval()
        param_count = sum(p.numel() for p in _nsfw_model.parameters()) / 1e6
        logger.info("✅ NSFW model loaded: %.1fM params on %s", param_count, _device)

    return _nsfw_model, _nsfw_processor, _device


def _detect_sync(image: Image.Image) -> NSFWResult:
    """Synchronous NSFW detection — call inside executor."""
    model, processor, device = _load_model()

    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)[0].cpu()

    # Get labels from model config
    id2label = model.config.id2label
    scores = {id2label[i]: float(probs[i]) for i in range(len(probs))}

    # Find top label
    top_label = max(scores, key=scores.get)
    top_confidence = scores[top_label]

    # Decision logic
    is_blocked = False
    is_safe = True

    if top_label in BLOCKED_LABELS and top_confidence >= CONFIDENCE_THRESHOLD:
        is_blocked = True
        is_safe = False
    elif top_label in WARNING_LABELS and top_confidence >= CONFIDENCE_THRESHOLD:
        # Warning but allow — log it
        logger.warning(
            "⚠️ NSFW warning: image classified as '%s' (%.2f)",
            top_label,
            top_confidence,
        )

    return NSFWResult(
        is_safe=is_safe,
        label=top_label,
        confidence=top_confidence,
        is_blocked=is_blocked,
        details=scores,
    )


async def check_image_safety(image: Image.Image) -> NSFWResult:
    """
    Проверяет изображение на NSFW-контент.

    Args:
        image: PIL Image (RGB)

    Returns:
        NSFWResult с флагами безопасности
    """
    if not image:
        return NSFWResult(
            is_safe=False,
            label="error",
            confidence=0.0,
            is_blocked=True,
            details={},
        )

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _detect_sync, image)
    except Exception as e:
        logger.warning("NSFW detection failed: %s", e)
        # Fail-safe: if detector breaks, assume safe to avoid blocking everything
        return NSFWResult(
            is_safe=True,
            label="error",
            confidence=0.0,
            is_blocked=False,
            details={"error": 1.0},
        )

    if result.is_blocked:
        logger.warning(
            "🚫 NSFW BLOCKED: label='%s' confidence=%.2f",
            result.label,
            result.confidence,
        )

    return result
