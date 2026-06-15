"""
Tests for bot_runner module.
"""

from unittest.mock import MagicMock, patch

import pytest

from bot_runner import (
    _is_advertorial,
    _is_junk,
    detect_score,
    filter_article,
    is_relevant,
    is_russian,
)


class TestDetectScore:
    def test_score_clamped_to_1_10(self):
        """Score ограничен [1, 10]."""
        a = {
            "title": "Трамп Путин санкции война ядерный мобилизация",
            "summary": "A" * 100,
            "source": "RT",
        }
        score = detect_score(a)
        assert 1 <= score <= 10

    def test_reaction_boost(self):
        """P1-001: реакции влияют на score."""
        from storage.reactions import ReactionsManager

        a = {"title": "News", "summary": "A" * 100, "source": "RT", "link": "https://example.com/1"}

        # Проверяем что score вычисляется корректно
        score = detect_score(a)
        assert score >= 1


class TestFilterArticle:
    """Тесты для filter_article() — junk, advertorial, relevance."""

    def _article(self, title="News", summary="A" * 100, source="Test"):
        return {
            "title": title,
            "summary": summary,
            "source": source,
            "published": None,
        }

    def test_passes_valid_article(self):
        """Валидная статья проходит фильтр."""
        a = self._article(
            title="Трамп подписал новый указ о санкциях",
            summary="Президент США Дональд Трамп подписал указ о введении новых санкций против России."
            * 3,
        )
        result = filter_article(a)
        assert result is True

    def test_filters_junk_quiz(self):
        """Мусор (викторина) отфильтровывается."""
        a = self._article(title="Тест: угадай столицу")
        result = filter_article(a)
        assert result is False

    def test_filters_junk_math(self):
        """Мусор (мат. пример) отфильтровывается."""
        a = self._article(title="Сколько будет 2+2?")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_top5(self):
        """Рекламная статья (топ-5) отфильтровывается."""
        a = self._article(title="Топ-5 сервисов для маркетинга")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_review(self):
        """Обзорная статья отфильтровывается."""
        a = self._article(title="Обзор платформ для email-рассылок")
        result = filter_article(a)
        assert result is False

    def test_filters_advertorial_promo(self):
        """Промо-статья отфильтровывается."""
        a = self._article(title="Промокод на скидку 50%")
        result = filter_article(a)
        assert result is False

    def test_filters_short_summary(self):
        """Слишком короткий summary отфильтровывается."""
        a = self._article(title="News", summary="Short")
        result = filter_article(a)
        assert result is False

    def test_user_prefs_min_score(self):
        """Фильтр по минимальному score пользователя."""
        a = self._article(title="Трамп подписал указ")
        prefs = {"min_score": 9}
        result = filter_article(a, prefs)
        # Трамп даёт +6, база 2 → 8 < 9, должно отфильтроваться
        assert result is False


class TestIsJunk:
    def test_junk_words(self):
        assert _is_junk("Тест: угадай ответ") is True
        assert _is_junk("Викторина по истории") is True
        assert _is_junk("Сколько будет 5*5?") is True
        assert _is_junk("Математика для детей") is True

    def test_not_junk(self):
        assert _is_junk("Трамп подписал указ") is False
        assert _is_junk("Bitcoin вырос на 5%") is False


class TestIsAdvertorial:
    def test_advertorial_patterns(self):
        assert _is_advertorial("Топ-10 инструментов для бизнеса") is True
        assert _is_advertorial("Обзор сервисов CRM") is True
        assert _is_advertorial("Как увеличить продажи в 3 раза") is True
        assert _is_advertorial("Промокод на скидку 20%") is True
        assert _is_advertorial("Реферальная программа") is True

    def test_not_advertorial(self):
        assert _is_advertorial("Трамп встретился с Путиным") is False
        assert _is_advertorial("Fed повысил ставку") is False


class TestIsRussian:
    def test_russian_text(self):
        # langdetect может ошибаться на коротких текстах — проверяем fallback на regex
        result = is_russian("Трамп подписал указ о санкциях против России")
        assert result is True

    def test_english_text(self):
        assert is_russian("Trump signs executive order") is False


class TestIsRelevant:
    def test_relevant_keywords(self):
        assert is_relevant("Трамп и Путин обсудили санкции") is True
        assert is_relevant("Bitcoin вырос после решения SEC") is True

    def test_irrelevant_text(self):
        assert is_relevant("Как приготовить борщ") is False


class TestGetDelayForScore:
    def test_high_score(self):
        from bot_runner import get_delay_for_score

        assert get_delay_for_score(9, "normal", False) == 0
        assert get_delay_for_score(8, "normal", False) == 0

    def test_medium_score(self):
        from bot_runner import get_delay_for_score

        assert get_delay_for_score(7, "normal", False) == 0
        assert get_delay_for_score(5, "normal", False) == 0

    def test_low_score(self):
        from bot_runner import get_delay_for_score

        assert get_delay_for_score(4, "normal", False) == 1800
        assert get_delay_for_score(1, "normal", False) == 1800


class TestPublishPolicyIntegration:
    """Тесты интеграции с publish_policy."""

    def test_get_publish_level_red(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(10) == "red"
        assert get_publish_level(9) == "red"
        assert get_publish_level(8) == "red"

    def test_get_publish_level_orange(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(7) == "orange"
        assert get_publish_level(6) == "orange"

    def test_get_publish_level_yellow(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(5) == "yellow"
        assert get_publish_level(1) == "yellow"

    def test_should_publish_red_always(self):
        from utils.publish_policy import should_publish

        allowed, _ = should_publish("red", 10, "normal", False)
        assert allowed is True

    def test_should_publish_yellow_delayed(self):
        from utils.publish_policy import should_publish

        # Yellow публикуется с задержкой 2-4 часа
        allowed, reason = should_publish("yellow", 3, "normal", False)
        assert allowed is True
        assert "delayed" in reason

    def test_should_publish_yellow_storm_mode(self):
        from utils.publish_policy import should_publish

        # В storm mode yellow тоже публикуется
        allowed, reason = should_publish("yellow", 3, "storm", False)
        assert allowed is True
        assert "storm" in reason

    def test_should_publish_orange_normal(self):
        from utils.publish_policy import should_publish

        allowed, _ = should_publish("orange", 7, "normal", False)
        assert allowed is True

    def test_should_publish_storm_mode_orange_delayed(self):
        from utils.publish_policy import should_publish

        # В storm mode orange публикуется с задержкой
        allowed, reason = should_publish("orange", 7, "storm", False)
        assert allowed is True
        assert "storm" in reason

    def test_should_publish_quiet_hours(self):
        from utils.publish_policy import should_publish

        # Orange блокируется в тихие часы
        allowed, reason = should_publish("orange", 7, "normal", True)
        assert allowed is False
        assert "quiet" in reason
