"""
Simple perceptual hash deduplication without numpy dependency.
Uses PIL-only average hash implementation.
"""

import io
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from PIL import Image

from utils.logger import logger

DB_PATH = "/root/smart_news_bot/storage/news_cache.db"
HASH_TABLE = "image_hashes"
SIMILARITY_THRESHOLD = 10  # max hamming distance
DEDUP_WINDOW_HOURS = 48


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {HASH_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phash TEXT NOT NULL,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{HASH_TABLE}_phash 
        ON {HASH_TABLE}(phash)
    """)
    conn.commit()
    return conn


def _compute_avg_hash(image_data: bytes, hash_size: int = 8) -> Optional[str]:
    """Compute average hash using only PIL."""
    try:
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Convert to grayscale and resize
        img = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        # Build binary hash
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        # Convert to hex
        return hex(int(bits, 2))[2:].zfill(hash_size * hash_size // 4)
    except Exception as e:
        logger.warning(f"Failed to compute hash: {e}")
        return None


def _hamming_distance(hex1: str, hex2: str) -> int:
    """Calculate hamming distance between two hex strings."""
    if len(hex1) != len(hex2):
        return 999
    try:
        int1 = int(hex1, 16)
        int2 = int(hex2, 16)
        x = int1 ^ int2
        distance = 0
        while x:
            distance += x & 1
            x >>= 1
        return distance
    except Exception:
        return 999


def is_image_duplicate(image_data: bytes) -> bool:
    """Check if image is visually similar to recently used ones."""
    phash_str = _compute_avg_hash(image_data)
    if not phash_str:
        return False

    conn = _get_db()
    try:
        cutoff = datetime.now() - timedelta(hours=DEDUP_WINDOW_HOURS)
        conn.execute(
            f"DELETE FROM {HASH_TABLE} WHERE created_at < ?",
            (cutoff.isoformat(),)
        )
        conn.commit()

        cursor = conn.execute(
            f"SELECT phash, url FROM {HASH_TABLE} WHERE created_at > ?",
            (cutoff.isoformat(),)
        )

        for row in cursor.fetchall():
            stored_hash = row[0]
            if not stored_hash:
                continue
            distance = _hamming_distance(phash_str, stored_hash)
            if distance <= SIMILARITY_THRESHOLD:
                logger.info(f"Duplicate image detected (distance={distance}, url={row[1]})")
                return True

        return False
    finally:
        conn.close()


def store_image_hash(image_data: bytes, url: str = ""):
    """Store hash of published image."""
    phash_str = _compute_avg_hash(image_data)
    if not phash_str:
        return

    conn = _get_db()
    try:
        conn.execute(
            f"INSERT INTO {HASH_TABLE} (phash, url) VALUES (?, ?)",
            (phash_str, url)
        )
        conn.commit()
    finally:
        conn.close()
