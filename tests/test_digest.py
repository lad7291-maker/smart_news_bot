"""
Tests for yellow digest builder (P1-005).
"""

import pytest

from core.scheduler_jobs import _build_digest_text


class TestDigestBuilder:
    def test_empty_articles(self):
        assert _build_digest_text([]) == ""

    def test_single_article(self):
        articles = [
            {
                "title": "Bitcoin вырос после решения SEC",
                "link": "https://example.com/1",
                "summary": "SEC одобрила ETF, цена превысила $70k.",
                "source": "CoinDesk",
            }
        ]
        text = _build_digest_text(articles)
        assert "📰 <b>Дайджест новостей</b>" in text
        assert "Bitcoin вырос" in text
        assert "https://example.com/1" in text
        assert "#CoinDesk" in text
        assert "₿" in text  # crypto emoji

    def test_grouping_by_emoji(self):
        """Статьи с одинаковым эмодзи должны быть сгруппированы."""
        articles = [
            {
                "title": "Bitcoin hits new high",
                "link": "https://example.com/btc",
                "summary": "BTC over 70k",
                "source": "CoinDesk",
            },
            {
                "title": "Ethereum upgrade live",
                "link": "https://example.com/eth",
                "summary": "ETH 2.0 deployed",
                "source": "CoinTelegraph",
            },
            {
                "title": "Fed raises rates",
                "link": "https://example.com/fed",
                "summary": "25bp hike",
                "source": "CNBC",
            },
        ]
        text = _build_digest_text(articles)
        # Crypto articles grouped under ₿
        assert text.count("₿") >= 2
        # Fed article under 🏦 or US
        assert ("🏦" in text) or ("🇺🇸" in text)

    def test_summary_truncation(self):
        """Очень длинный summary должен обрезаться."""
        articles = [
            {
                "title": "Short title",
                "link": "https://example.com/1",
                "summary": "Word " * 100,
                "source": "Test",
            }
        ]
        text = _build_digest_text(articles)
        # Summary should be truncated to ~120 chars
        lines = text.split("\n")
        summary_line = [l for l in lines if l.strip().startswith("<i>")]
        if summary_line:
            assert len(summary_line[0]) <= 150

    def test_max_10_articles(self):
        """Не более 10 новостей в дайджесте."""
        articles = [
            {
                "title": f"News {i}",
                "link": f"https://example.com/{i}",
                "summary": "",
                "source": "Test",
            }
            for i in range(15)
        ]
        text = _build_digest_text(articles)
        # Should not contain news 11-15
        assert "News 11" not in text
        assert "News 9" in text

    def test_truncate_over_4000(self):
        """Текст длиннее 4000 символов должен обрезаться."""
        articles = [
            {
                "title": f"Very long title number {i} with many words to consume space",
                "link": f"https://example.com/{i}",
                "summary": "Summary text here with some extra words " * 5,
                "source": "TestSource",
            }
            for i in range(20)
        ]
        text = _build_digest_text(articles)
        assert len(text) <= 4100
        assert "…" in text or "и ещё" in text

    def test_no_link_no_crash(self):
        """Статья без ссылки не должна падать."""
        articles = [{"title": "No link news", "link": "", "summary": "", "source": "Test"}]
        text = _build_digest_text(articles)
        assert "No link news" in text
        assert "🔗" not in text

    def test_short_summary_ignored(self):
        """Summary короче 30 символов не показывается."""
        articles = [
            {
                "title": "Title",
                "link": "https://example.com/1",
                "summary": "Short",
                "source": "Test",
            }
        ]
        text = _build_digest_text(articles)
        assert "Short" not in text
