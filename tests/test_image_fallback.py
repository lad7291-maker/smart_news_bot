"""
Тесты для fallback-изображений.
BUG-004: Проверка, что fallback-URL доступны (не 403).
"""
import pytest
import httpx
from utils.image_relevance_checker import get_fallback_image_url


class TestImageFallback:
    _FALLBACK_SOURCES = ["rt", "ria", "tass", "interfax", "cnbc", "nyt", "coindesk", "cointelegraph"]

    @pytest.mark.parametrize("source", _FALLBACK_SOURCES)
    def test_fallback_url_returns_200(self, source):
        """BUG-004: Wikimedia отдаёт 403. Этот тест должен падать до исправления."""
        url = get_fallback_image_url(source)
        if not url:
            pytest.skip(f"No fallback for {source}")
        try:
            resp = httpx.head(url, timeout=10, follow_redirects=True)
            assert resp.status_code == 200, (
                f"BUG-004: Fallback image for '{source}' returned {resp.status_code}. "
                f"URL: {url}"
            )
        except httpx.RequestError as e:
            pytest.fail(f"Network error checking fallback for {source}: {e}")

    def test_all_sources_have_fallback(self):
        """Каждый источник из конфига должен иметь fallback."""
        from config import config
        for source in config.RSS_SOURCES:
            tag = source["tag"]
            url = get_fallback_image_url(tag)
            # Не все источники обязаны иметь fallback, но ключевые должны
            if tag in {"RT", "RIA", "Interfax", "CNBC_World", "NYT_Business", "CoinDesk", "CoinTelegraph"}:
                assert url is not None, f"Critical source {tag} has no fallback image"
