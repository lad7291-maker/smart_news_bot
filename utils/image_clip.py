"""
CLIP-based semantic relevance scoring for news images.

Uses openai/clip-vit-base-patch32 (151M params) to compute cosine similarity
between image pixels and news headline text. Runs locally, zero cost.

Typical scores:
- 0.25-0.30: weak relevance (e.g. generic stock photo)
- 0.30-0.35: moderate relevance
- 0.35+: strong relevance (image directly depicts headline subject)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

# FIX: PyTorch 2.12 oneDNN bug на CPU — отключаем MKL-DNN
# https://github.com/pytorch/pytorch/issues/...
torch.backends.mkldnn.enabled = False
torch.set_num_threads(1)

logger = logging.getLogger(__name__)

# Lazy-loaded singletons
_clip_model: Optional[CLIPModel] = None
_clip_processor: Optional[CLIPProcessor] = None
_device: Optional[str] = None

# Model name — base patch32 is fast and good enough
MODEL_NAME = "openai/clip-vit-base-patch32"

# Score thresholds
RELEVANCE_WEAK = 0.25
RELEVANCE_MODERATE = 0.30
RELEVANCE_STRONG = 0.35


@dataclass
class CLIPScoreResult:
    """Результат оценки релевантности через CLIP."""

    score: float  # 0.0 - 1.0, cosine similarity
    is_relevant: bool  # score >= RELEVANCE_MODERATE
    label: str  # "strong", "moderate", "weak", "none"


def _load_model() -> tuple[CLIPModel, CLIPProcessor, str]:
    """Lazy-load CLIP model and processor. Thread-safe via module-level caching."""
    global _clip_model, _clip_processor, _device

    if _clip_model is None:
        logger.info("🔄 Loading CLIP model (%s)...", MODEL_NAME)
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _clip_model = CLIPModel.from_pretrained(MODEL_NAME).to(_device).eval()
        _clip_processor = CLIPProcessor.from_pretrained(MODEL_NAME)
        param_count = sum(p.numel() for p in _clip_model.parameters()) / 1e6
        logger.info("✅ CLIP loaded: %.1fM params on %s", param_count, _device)

    return _clip_model, _clip_processor, _device


def _score_sync(image: Image.Image, text: str) -> float:
    """Synchronous CLIP scoring — call inside executor."""
    model, processor, device = _load_model()

    # Truncate text to CLIP's max length (77 tokens ~ ~250 chars)
    text = text.strip()[:200]

    inputs = processor(
        text=[text],
        images=image,
        return_tensors="pt",
        padding=True,
        truncation=True,  # P3-006: обрезка токенов до 77 для CLIP
        max_length=77,
    )
    # Move to device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        # logits_per_image: [1, 1] — similarity score
        score = outputs.logits_per_image[0][0].item()
        # Normalize to [0, 1] using sigmoid with temperature
        # CLIP logits for matching pairs: typically 20-35
        # CLIP logits for non-matching: typically 15-25 (still high due to model bias)
        # We use a tighter sigmoid to spread the range
        # score=20 -> ~0.12, score=25 -> ~0.50, score=30 -> ~0.88
        normalized = torch.sigmoid(torch.tensor((score - 25.0) / 3.0)).item()

    return normalized


async def score_image_relevance(image: Image.Image, title: str) -> CLIPScoreResult:
    """
    Оценивает семантическую релевантность изображения заголовку через CLIP.

    Args:
        image: PIL Image (RGB)
        title: Заголовок новости

    Returns:
        CLIPScoreResult с числовым score и категорией
    """
    if not title or not image:
        return CLIPScoreResult(score=0.0, is_relevant=False, label="none")

    try:
        loop = asyncio.get_event_loop()
        score = await loop.run_in_executor(None, _score_sync, image, title)
    except Exception as e:
        logger.warning("CLIP scoring failed: %s", e)
        return CLIPScoreResult(score=0.0, is_relevant=False, label="error")

    if score >= RELEVANCE_STRONG:
        label = "strong"
    elif score >= RELEVANCE_MODERATE:
        label = "moderate"
    elif score >= RELEVANCE_WEAK:
        label = "weak"
    else:
        label = "none"

    is_relevant = score >= RELEVANCE_MODERATE

    logger.debug(
        "CLIP score: %.3f (%s) for '%s...'",
        score,
        label,
        title[:40],
    )

    return CLIPScoreResult(score=score, is_relevant=is_relevant, label=label)


async def batch_score_images(
    images: list[Image.Image],
    titles: list[str],
) -> list[CLIPScoreResult]:
    """
    Batch scoring for multiple images. More efficient than sequential calls.
    """
    if len(images) != len(titles):
        raise ValueError("images and titles must have same length")

    if not images:
        return []

    try:
        model, processor, device = _load_model()

        # Truncate all texts
        texts = [t.strip()[:250] for t in titles]

        inputs = processor(
            text=texts,
            images=images,
            return_tensors="pt",
            padding=True,
            truncation=True,  # P3-006: обрезка токенов до 77 для CLIP
            max_length=77,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        def _run():
            with torch.no_grad():
                outputs = model(**inputs)
                # logits_per_image: [N, N] diagonal is self-similarities
                scores = torch.diagonal(outputs.logits_per_image).cpu()
                normalized = torch.sigmoid((scores - 25.0) / 3.0).numpy()
            return normalized

        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(None, _run)

        results = []
        for score in scores:
            s = float(score)
            if s >= RELEVANCE_STRONG:
                label = "strong"
            elif s >= RELEVANCE_MODERATE:
                label = "moderate"
            elif s >= RELEVANCE_WEAK:
                label = "weak"
            else:
                label = "none"
            results.append(
                CLIPScoreResult(score=s, is_relevant=s >= RELEVANCE_MODERATE, label=label)
            )

        return results

    except Exception as e:
        logger.warning("CLIP batch scoring failed: %s", e)
        return [CLIPScoreResult(score=0.0, is_relevant=False, label="error") for _ in images]
