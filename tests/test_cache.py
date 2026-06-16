"""
Tests for cache manager.
FEAT-013: SQLite cache operations.
"""

import pytest

from storage.cache import CacheManager


class TestCacheManager:
    def test_mark_and_check_processed(self, tmp_db_path):
        cache = CacheManager(db_path=tmp_db_path)
        link = "https://example.com/news/1"
        assert cache.is_processed(link) is False
        cache.mark_processing(link, "rss", "Test", "Title")
        cache.mark_processed(link, success=True)
        assert cache.is_processed(link) is True
        cache.close()

    def test_title_duplicate_detection(self, tmp_db_path):
        cache = CacheManager(db_path=tmp_db_path)
        title1 = "Bitcoin price rises sharply after ETF approval"
        cache.mark_processing("https://example.com/1", "rss", "Test", title1)
        cache.mark_processed("https://example.com/1", success=True)
        # Same story, different URL
        assert cache.is_title_processed(title1, hours=24) is True
        cache.close()

    def test_stats_after_insert(self, tmp_db_path):
        cache = CacheManager(db_path=tmp_db_path)
        cache.mark_processing("https://a.com", "rss", "A", "Title A")
        cache.mark_processed("https://a.com", success=True)
        stats = cache.get_processing_stats()
        assert stats["processed"] >= 1
        cache.close()

    def test_image_used_tracking(self, tmp_db_path):
        cache = CacheManager(db_path=tmp_db_path)
        img_url = "https://example.com/photo.jpg"
        assert cache.is_image_used(img_url, hours=24) is False
        cache.mark_image_used(img_url)
        assert cache.is_image_used(img_url, hours=24) is True
        assert cache.is_image_used(img_url, hours=0) is False
        cache.close()
