"""
Модуль обработки изображений перед публикацией.

Функции:
1. Проверка доступности изображения (HEAD запрос)
2. Проверка "свежести" изображения (HTTP Last-Modified / Exif DateTime)
3. Обрезка под соотношение сторон Telegram (16:9 для постов, 1:1 для превью)
4. Наложение водяного знака
5. Генерация alt-текста через LLM
"""

import hashlib
import io
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from config import config
from utils.image_clip import CLIPScoreResult, score_image_relevance
from utils.image_nsfw import NSFWResult, check_image_safety
from utils.logger import logger

# --- Кэш на диске ---
IMAGE_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "image_cache")
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
CACHE_MAX_AGE_HOURS = 24

# --- Константы ---
TELEGRAM_POST_ASPECT = 16 / 9  # Горизонтальное превью поста
TELEGRAM_PREVIEW_ASPECT = 1.0  # Квадратное превью канала
MAX_IMAGE_WIDTH = 1920
MAX_IMAGE_HEIGHT = 1080
JPEG_QUALITY = 85

# Порог "старости" изображения — 2 года
MAX_IMAGE_AGE_DAYS = 730

logger = logging.getLogger(__name__)


@dataclass
class ImageCheckResult:
    """Результат проверки изображения."""

    url: str
    is_accessible: bool
    is_fresh: bool
    content_type: Optional[str]
    last_modified: Optional[datetime]
    size_bytes: Optional[int]
    width: Optional[int]
    height: Optional[int]
    error: Optional[str] = None


async def check_image_freshness(url: str, timeout: float = 10.0) -> ImageCheckResult:
    """
    Проверяет доступность и "свежесть" изображения по HTTP заголовкам.

    Returns:
        ImageCheckResult с флагами is_accessible и is_fresh
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            # HEAD запрос для проверки заголовков
            resp = await client.head(url, headers={"User-Agent": config.USER_AGENT})

            if resp.status_code in (403, 405):
                # Пробуем GET для CDN, которые блокируют HEAD
                resp = await client.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=2.0)
                # Читаем первые байты и закрываем
                if resp.status_code == 200:
                    _ = resp.content[:1024]

            if resp.status_code not in (200, 204):
                return ImageCheckResult(
                    url=url,
                    is_accessible=False,
                    is_fresh=False,
                    content_type=None,
                    last_modified=None,
                    size_bytes=None,
                    width=None,
                    height=None,
                    error=f"HTTP {resp.status_code}",
                )

            content_type = resp.headers.get("content-type", "").lower()
            size_bytes = resp.headers.get("content-length")
            size_bytes = int(size_bytes) if size_bytes and size_bytes.isdigit() else None

            # Проверяем Last-Modified
            last_modified_str = resp.headers.get("last-modified")
            last_modified = None
            is_fresh = True  # По умолчанию считаем свежим, если не удалось проверить

            if last_modified_str:
                try:
                    # Формат: Wed, 21 Oct 2015 07:28:00 GMT
                    last_modified = datetime.strptime(
                        last_modified_str, "%a, %d %b %Y %H:%M:%S %Z"
                    ).replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - last_modified).days
                    is_fresh = age_days <= MAX_IMAGE_AGE_DAYS
                    if not is_fresh:
                        logger.info(f"🕰 Изображение устарело ({age_days} дней): {url[:60]}...")
                except ValueError:
                    pass

            return ImageCheckResult(
                url=url,
                is_accessible=True,
                is_fresh=is_fresh,
                content_type=content_type,
                last_modified=last_modified,
                size_bytes=size_bytes,
                width=None,
                height=None,
            )

    except Exception as e:
        logger.debug(f"Image check failed for {url[:60]}: {e}")
        return ImageCheckResult(
            url=url,
            is_accessible=False,
            is_fresh=False,
            content_type=None,
            last_modified=None,
            size_bytes=None,
            width=None,
            height=None,
            error=str(e),
        )


async def download_image(url: str, timeout: float = 15.0) -> Optional[Image.Image]:
    """Скачивает изображение и возвращает PIL Image."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": config.USER_AGENT})
            if resp.status_code in (403, 405):
                # Fallback for servers blocking default requests
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": config.USER_AGENT,
                        "Referer": "https://www.interfax.ru/",
                    },
                )
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            # Конвертируем в RGB для единообразия
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            return img
    except (UnidentifiedImageError, httpx.HTTPError, Exception) as e:
        logger.debug(f"Download image failed: {e}")
        return None


def crop_to_aspect(img: Image.Image, aspect_ratio: float) -> Image.Image:
    """Обрезает изображение до заданного соотношения сторон (центрированно)."""
    width, height = img.size
    current_aspect = width / height

    if abs(current_aspect - aspect_ratio) < 0.05:
        # Уже близко к нужному — не обрезаем
        return img

    if current_aspect > aspect_ratio:
        # Слишком широкое — обрезаем по ширине
        new_width = int(height * aspect_ratio)
        left = (width - new_width) // 2
        img = img.crop((left, 0, left + new_width, height))
    else:
        # Слишком высокое — обрезаем по высоте
        new_height = int(width / aspect_ratio)
        top = (height - new_height) // 2
        img = img.crop((0, top, width, top + new_height))

    return img


def resize_if_needed(
    img: Image.Image, max_width: int = MAX_IMAGE_WIDTH, max_height: int = MAX_IMAGE_HEIGHT
) -> Image.Image:
    """Уменьшает изображение, если оно слишком большое."""
    width, height = img.size
    if width <= max_width and height <= max_height:
        return img

    # Сохраняем пропорции
    ratio = min(max_width / width, max_height / height)
    new_size = (int(width * ratio), int(height * ratio))
    return img.resize(new_size, Image.LANCZOS)


def add_watermark(img: Image.Image, text: str = "Smart News") -> Image.Image:
    """Накладывает полупрозрачный водяной знак в правом нижнем углу."""
    draw = ImageDraw.Draw(img)

    # Размер шрифта пропорционально изображению
    font_size = max(12, img.width // 40)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Размеры текста
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Позиция: правый нижний угол с отступом
    padding = max(10, img.width // 60)
    x = img.width - text_width - padding
    y = img.height - text_height - padding

    # Полупрозрачный фон
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
        fill=(0, 0, 0, 80),
    )
    overlay_draw.text((x, y), text, font=font, fill=(255, 255, 255, 180))

    # Композитинг
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def generate_branded_image(
    title: str, summary: str = "", width: int = 1280, height: int = 720
) -> bytes:
    """Генерирует branded image с заголовком и watermark для поста без фото."""
    # Use video frame as background if available
    frame_path = "/tmp/branded_frame.png"
    if os.path.exists(frame_path):
        img = Image.open(frame_path).convert("RGB").resize((width, height), Image.LANCZOS)
        # Darken the background for text readability
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 180))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")
    else:
        img = Image.new("RGB", (width, height), (15, 23, 30))
    draw = ImageDraw.Draw(img)

    # Try to load a nice font, fallback to default
    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(24, width // 35)
        )
        body_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(16, width // 50)
        )
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    # Draw title
    margin = width // 15
    y = height // 4
    max_width = width - 2 * margin

    # Wrap text
    words = title.split()
    lines = []
    current_line = ""
    for word in words:
        test = current_line + " " + word if current_line else word
        bbox = draw.textbbox((0, 0), test, font=title_font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    # Draw lines
    for line in lines[:5]:  # Max 5 lines
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = (width - line_width) // 2
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += line_height + 10

    # Add watermark
    img = add_watermark(img, text="@SmartNewsAI")

    return image_to_bytes(img)


def image_to_bytes(img: Image.Image, format: str = "JPEG", quality: int = JPEG_QUALITY) -> bytes:
    """Конвертирует PIL Image в bytes для отправки в Telegram."""
    buffer = io.BytesIO()
    if format.upper() == "JPEG":
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
    else:
        img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def _get_cache_path(image_url: str) -> str:
    """Возвращает путь к кэш-файлу для URL изображения."""
    url_hash = hashlib.md5(image_url.encode()).hexdigest()
    return os.path.join(IMAGE_CACHE_DIR, f"{url_hash}.jpg")


def _is_cache_valid(cache_path: str) -> bool:
    """Проверяет, не устарел ли кэш."""
    if not os.path.exists(cache_path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(cache_path), tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    return age < timedelta(hours=CACHE_MAX_AGE_HOURS)


def _save_to_cache(cache_path: str, image_bytes: bytes) -> None:
    """Сохраняет обработанное изображение в кэш."""
    try:
        with open(cache_path, "wb") as f:
            f.write(image_bytes)
    except Exception as e:
        logger.debug(f"Не удалось сохранить кэш изображения: {e}")


def _load_from_cache(cache_path: str) -> Optional[bytes]:
    """Загружает изображение из кэша."""
    try:
        with open(cache_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Не удалось загрузить кэш изображения: {e}")
        return None


async def process_image_for_telegram(
    image_url: str,
    article_title: str = "",
    source: str = "",
    add_wm: bool = True,
    target_aspect: float = TELEGRAM_POST_ASPECT,
    check_clip: bool = True,
    check_nsfw: bool = True,
    min_clip_score: float = 0.25,
    trusted_domain: bool = False,
) -> Optional[bytes]:
    """
    Полный pipeline обработки изображения для Telegram.

    1. Проверяет кэш
    2. Проверяет доступность и свежесть
    3. Скачивает
    4. CLIP: проверяет семантическую релевантность заголовку
    5. NSFW: проверяет на неприемлемый контент
    6. Обрезает под соотношение сторон (16:9 для поста, 1:1 для превью)
    7. Уменьшает, если слишком большое
    8. Накладывает водяной знак (если не из официального RSS)
    9. Конвертирует в JPEG bytes
    10. Сохраняет в кэш

    Args:
        image_url: URL изображения
        article_title: Заголовок статьи (для CLIP)
        source: Источник изображения (rss, og, article, searxng)
        add_wm: Накладывать водяной знак
        target_aspect: Целевое соотношение сторон
        check_clip: Проверять релевантность через CLIP
        check_nsfw: Проверять на NSFW
        min_clip_score: Минимальный CLIP score (0.0-1.0)

    Returns:
        JPEG bytes или None если не удалось обработать
    """
    # Шаг 0: Проверка кэша
    cache_path = _get_cache_path(image_url)
    if _is_cache_valid(cache_path):
        cached = _load_from_cache(cache_path)
        if cached:
            logger.debug(f"💾 Изображение из кэша: {image_url[:60]}...")
            return cached

    # Шаг 0b: Проверка кэша скриншотов (если URL — это статья, а не изображение)
    from utils.screenshot_generator import _get_cache_path as _get_screenshot_cache_path
    from utils.screenshot_generator import _is_cache_valid as _is_screenshot_cache_valid

    screenshot_cache = _get_screenshot_cache_path(image_url)
    if _is_screenshot_cache_valid(screenshot_cache):
        logger.debug(f"💾 Скриншот из кэша: {image_url[:60]}...")
        with open(screenshot_cache, "rb") as f:
            screenshot_bytes = f.read()
        # Конвертируем PNG скриншот в JPEG
        try:
            img = Image.open(__import__("io").BytesIO(screenshot_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img = crop_to_aspect(img, target_aspect)
            img = resize_if_needed(img)
            # Скриншоты без водяного знака (это скриншот источника)
            result = image_to_bytes(img, format="JPEG", quality=85)
            _save_to_cache(cache_path, result)
            return result
        except Exception as e:
            logger.warning(f"Screenshot cache processing failed: {e}")

    # Шаг 1: Проверка доступности
    check = await check_image_freshness(image_url)
    if not check.is_accessible:
        logger.info(f"🚫 Изображение недоступно ({check.error}): {image_url[:60]}...")
        return None

    if not check.is_fresh:
        logger.info(f"🚫 Изображение устарело: {image_url[:60]}...")
        # Не отбрасываем полностью, но логируем

    # Шаг 2: Скачивание
    img = await download_image(image_url)
    if img is None:
        return None

    # Шаг 3: CLIP — семантическая релевантность (P3-006: truncation до 200 символов для 77 токенов CLIP)
    if check_clip and article_title:
        try:
            clip_result = await score_image_relevance(img, article_title)
            if clip_result.score < min_clip_score:
                # Для доверенных новостных доменов не отклоняем — фото от AP/Reuters/Getty
                # часто не проходят CLIP (люди в костюмах, здания бирж), но это реальные фото
                if trusted_domain:
                    logger.info(
                        f"⚠️ CLIP низкий score ({clip_result.score:.3f}) для доверенного домена, пропускаем: {image_url[:60]}..."
                    )
                else:
                    logger.info(
                        f"🚫 CLIP отклонил изображение (score={clip_result.score:.3f} < {min_clip_score}): {image_url[:60]}..."
                    )
                    return None
            logger.debug(
                f"✅ CLIP score={clip_result.score:.3f} ({clip_result.label}): {image_url[:60]}..."
            )
        except Exception as e:
            logger.warning(f"CLIP check failed, skipping: {e}")

    # Шаг 4: NSFW — проверка на неприемлемый контент
    if check_nsfw:
        try:
            nsfw_result = await check_image_safety(img)
            if nsfw_result.is_blocked:
                logger.warning(
                    f"🚫 NSFW BLOCKED ({nsfw_result.label}={nsfw_result.confidence:.2f}): {image_url[:60]}..."
                )
                return None
            logger.debug(
                f"✅ NSFW safe ({nsfw_result.label}={nsfw_result.confidence:.2f}): {image_url[:60]}..."
            )
        except Exception as e:
            logger.warning(f"NSFW check failed, skipping: {e}")

    # Шаг 5: Обрезка под соотношение сторон
    # Сначала 1:1 для квадратного превью канала (Telegram показывает квадрат в списке)
    # Затем 16:9 для самого поста
    img_preview = crop_to_aspect(img.copy(), TELEGRAM_PREVIEW_ASPECT)
    img_post = crop_to_aspect(img, target_aspect)

    # Используем 16:9 для поста
    img = img_post

    # Шаг 6: Уменьшение, если слишком большое
    img = resize_if_needed(img)

    # Шаг 7: Водяной знак (не для изображений из официальных RSS источников)
    if add_wm and source not in ("rss", "og"):
        img = add_watermark(img, text="@SmartNewsAI")

    # Шаг 8: Конвертация в bytes
    result = image_to_bytes(img)

    # Шаг 9: Сохранение в кэш
    _save_to_cache(cache_path, result)

    return result


async def generate_alt_text(title: str, summary: str = "", image_url: str = "") -> str:
    """
    Генерирует alt-текст для изображения.

    Простая реализация: использует заголовок + ключевые слова.
    В будущем можно заменить на BLIP или LLM-вызов.
    """
    if not title:
        return "Новостное изображение"

    # Очищаем заголовок
    alt = title.strip()
    if len(alt) > 200:
        alt = alt[:197] + "..."

    return f"Изображение к новости: {alt}"
