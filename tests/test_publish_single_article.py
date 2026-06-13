"""
Tests for publish_single_article (P1-005).
Моки: bot.send_photo, cache_manager, analyze_news, find_news_image.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.scheduler_jobs import publish_single_article, set_scheduler_dependencies


class TestPublishSingleArticle:
    """Тесты публикации одной новости."""

    def setup_method(self):
        """Настройка моков перед каждым тестом."""
        self.mock_bot = AsyncMock()
        self.mock_cache = MagicMock()
        self.mock_cache.is_processed.return_value = False
        self.mock_cache._generate_hash.return_value = "hash123"
        self.mock_scheduler = MagicMock()

        set_scheduler_dependencies(
            bot=self.mock_bot,
            cache_manager=self.mock_cache,
            scheduler=self.mock_scheduler,
            parser=MagicMock(),
            config=MagicMock(),
            SCORE_DELAYS={"high": 150, "medium": 390, "low": 14400},
        )

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.send_multiple_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.analyze_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.find_news_image", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.is_russian")
    @patch("core.scheduler_jobs.publish_policy")
    async def test_publish_success(
        self, mock_policy, mock_is_russian, mock_find_image, mock_analyze, mock_send
    ):
        """Успешная публикация статьи."""
        mock_policy.get_publish_level.return_value = "red"
        mock_policy.get_mode.return_value = "normal"
        mock_policy.is_quiet_hours.return_value = False
        mock_policy.should_publish.return_value = (True, "")
        mock_policy.check_topic_cooldown.return_value = (True, "", 0)

        mock_is_russian.return_value = True  # Не требует перевода
        mock_analyze.return_value = "AI comment"
        mock_find_image.return_value = "https://example.com/image.jpg"
        mock_send.return_value = None

        article = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Summary text",
            "source": "TestSource",
            "score": 9,
        }

        await publish_single_article(article)

        # Проверяем, что отправили
        mock_send.assert_called_once()
        sent_article = mock_send.call_args[0][0][0]
        assert sent_article["ai_comment"] == "AI comment"
        assert sent_article["image_url"] == "https://example.com/image.jpg"

        # Пометили как обработанную
        self.mock_cache.mark_processed.assert_called_with(
            "https://example.com/article", success=True
        )

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.publish_policy")
    async def test_skip_already_processed(self, mock_policy):
        """Пропуск уже опубликованной статьи."""
        self.mock_cache.is_processed.return_value = True

        article = {
            "title": "Test",
            "link": "https://example.com/article",
            "score": 5,
        }

        await publish_single_article(article)

        # Не должно быть вызовов отправки
        self.mock_cache.mark_processed.assert_not_called()

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.publish_policy")
    async def test_skip_no_link(self, mock_policy):
        """Пропуск статьи без ссылки."""
        article = {
            "title": "Test",
            "link": "",
            "score": 5,
        }

        await publish_single_article(article)

        self.mock_cache.mark_processed.assert_not_called()

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.publish_policy")
    async def test_policy_blocks_low_score(self, mock_policy):
        """Политика блокирует публикацию (откладывает)."""
        mock_policy.get_publish_level.return_value = "yellow"
        mock_policy.get_mode.return_value = "normal"
        mock_policy.is_quiet_hours.return_value = False
        mock_policy.should_publish.return_value = (False, "quiet_hours")
        mock_policy.get_delay_seconds.return_value = 3600

        article = {
            "title": "Test",
            "link": "https://example.com/article",
            "score": 3,
        }

        await publish_single_article(article)

        # Должна быть добавлена отложенная задача
        self.mock_scheduler.add_job.assert_called_once()
        self.mock_cache.mark_processed.assert_not_called()  # Не помечаем как обработанную

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.send_multiple_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.analyze_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.find_news_image", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.is_russian")
    @patch("core.scheduler_jobs.publish_policy")
    async def test_translation_before_publish(
        self, mock_policy, mock_is_russian, mock_find_image, mock_analyze, mock_send
    ):
        """Перевод перед публикацией для не-русских статей."""
        mock_policy.get_publish_level.return_value = "red"
        mock_policy.get_mode.return_value = "normal"
        mock_policy.is_quiet_hours.return_value = False
        mock_policy.should_publish.return_value = (True, "")
        mock_policy.check_topic_cooldown.return_value = (True, "", 0)

        mock_is_russian.return_value = False  # Требует перевода
        mock_analyze.return_value = "AI comment"
        mock_find_image.return_value = None
        mock_send.return_value = None

        with patch(
            "core.scheduler_jobs.translate_to_russian", new_callable=AsyncMock
        ) as mock_translate:
            mock_translate.return_value = "Переведённый заголовок"

            article = {
                "title": "English Title",
                "link": "https://example.com/article",
                "summary": "English summary",
                "source": "TestSource",
                "score": 9,
            }

            await publish_single_article(article)

            # Перевод был вызван
            assert mock_translate.call_count >= 1

    @pytest.mark.asyncio
    @patch("core.scheduler_jobs.send_multiple_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.analyze_news", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.find_news_image", new_callable=AsyncMock)
    @patch("core.scheduler_jobs.is_russian")
    @patch("core.scheduler_jobs.publish_policy")
    async def test_existing_image_no_search(
        self, mock_policy, mock_is_russian, mock_find_image, mock_analyze, mock_send
    ):
        """Если изображение уже есть в RSS — не ищем через SearXNG."""
        mock_policy.get_publish_level.return_value = "red"
        mock_policy.get_mode.return_value = "normal"
        mock_policy.is_quiet_hours.return_value = False
        mock_policy.should_publish.return_value = (True, "")
        mock_policy.check_topic_cooldown.return_value = (True, "", 0)

        mock_is_russian.return_value = True
        mock_analyze.return_value = "AI comment"
        mock_send.return_value = None

        article = {
            "title": "Test",
            "link": "https://example.com/article",
            "summary": "Summary",
            "source": "TestSource",
            "score": 9,
            "image_url": "https://rss.com/image.jpg",
            "image_source": "rss",
            "image_score": 75,  # Высокий score — не ищем через SearXNG
        }

        await publish_single_article(article)

        # Использовали существующее (высокий score — без поиска)
        sent_article = mock_send.call_args[0][0][0]
        assert sent_article["image_url"] == "https://rss.com/image.jpg"
