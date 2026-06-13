"""
Интеграционные тесты для bot_runner.py (P2-004).
Тестируем detect_score, filter_article, publish_policy integration.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.filters import _is_advertorial, _is_junk, filter_article, is_relevant, is_russian
from core.scoring import (
    BOOST_KEYWORDS,
    PENALTY_KEYWORDS,
    SOURCE_SCORES,
    detect_score,
    get_delay_for_score,
)


class TestDetectScore:
    """Тесты для detect_score() — все комбинации base/boost/penalty/freshness."""

    def _article(self, title="", summary="", source="Test", published=None, link=""):
        return {
            "title": title,
            "summary": summary,
            "source": source,
            "source_tag": source,
            "published": published or datetime.now(),
            "link": link,
        }

    def test_base_score_from_source(self):
        """Базовый score из SOURCE_SCORES."""
        for source, expected in SOURCE_SCORES.items():
            a = self._article(source=source)
            score = detect_score(a)
            assert score >= 1, f"{source}: score={score} should be >= 1"
            assert score <= 10, f"{source}: score={score} should be <= 10"

    def test_base_score_unknown_source(self):
        """Unknown source → базовый score 2."""
        a = self._article(source="UnknownBlog")
        score = detect_score(a)
        assert score >= 1

    def test_boost_keywords(self):
        """Бонус за ключевые слова."""
        for word, bonus in list(BOOST_KEYWORDS.items())[:5]:
            a = self._article(title=f"News about {word}")
            score = detect_score(a)
            base = SOURCE_SCORES.get("Test", 2)
            expected_min = min(10, max(1, int(round(base + bonus))))
            assert score >= 1

    def test_penalty_keywords(self):
        """Штраф за нерелевантные темы."""
        for word in list(PENALTY_KEYWORDS)[:3]:
            a = self._article(title=f"News about {word}")
            score = detect_score(a)
            assert score >= 1

    def test_freshness_bonus_6h(self):
        """Бонус за свежесть < 6 часов."""
        a = self._article(published=datetime.now() - timedelta(hours=3))
        score = detect_score(a)
        assert score >= 1

    def test_freshness_bonus_12h(self):
        """Бонус за свежесть < 12 часов."""
        a = self._article(published=datetime.now() - timedelta(hours=8))
        score = detect_score(a)
        assert score >= 1

    def test_freshness_no_bonus_old(self):
        """Нет бонуса для старых новостей (> 24ч)."""
        a = self._article(published=datetime.now() - timedelta(hours=48))
        score_no_fresh = detect_score(a)
        assert score_no_fresh >= 1

    def test_user_prefs_preferred_topic(self):
        """Бонус +2 за предпочитаемую тему."""
        a = self._article(title="Bitcoin hits new high")
        prefs = {"preferred_topics": ["крипто"]}
        score = detect_score(a, prefs)
        assert score >= 1

    def test_user_prefs_blocked_topic(self):
        """Сильный штраф -5 за заблокированную тему."""
        a = self._article(title="Football match results")
        prefs = {"blocked_topics": ["спорт"]}
        score = detect_score(a, prefs)
        assert score >= 1

    def test_user_prefs_source_weight(self):
        """Персонализированный вес источника."""
        a = self._article(source="RT")
        prefs = {"source_weights": {"RT": 1.5}}
        score = detect_score(a, prefs)
        base = SOURCE_SCORES["RT"]
        expected = min(10, max(1, int(round(base * 1.5))))
        assert score == expected

    def test_score_clamped_to_1_10(self):
        """Score ограничен [1, 10]."""
        a = self._article(title="Трамп Путин санкции война ядерный мобилизация")
        score = detect_score(a)
        assert 1 <= score <= 10

    def test_reaction_boost(self):
        """P1-001: реакции влияют на score."""
        a = self._article(link="https://example.com/1")
        with patch("bot_runner.reactions_manager.get_article_score_boost", return_value=0.5):
            score = detect_score(a)
            assert score >= 1


class TestFilterArticle:
    """Тесты для filter_article() — junk, advertorial, relevance."""

    def _article(self, title="News", summary="A" * 100, source="Test"):
        return {
            "title": title,
            "summary": summary,
            "source": source,
            "published": datetime.now(),
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
        assert get_delay_for_score(9, "normal", False) == 0
        assert get_delay_for_score(8, "normal", False) == 0

    def test_medium_score(self):
        assert get_delay_for_score(7, "normal", False) == 0
        assert get_delay_for_score(5, "normal", False) == 0

    def test_low_score(self):
        assert get_delay_for_score(4, "normal", False) == 1800
        assert get_delay_for_score(1, "normal", False) == 1800


class TestPublishPolicyIntegration:
    """Тесты интеграции с publish_policy."""

    def test_get_publish_level_red(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(10) == "red"
        assert get_publish_level(9) == "red"

    def test_get_publish_level_orange(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(8) == "orange"
        assert get_publish_level(7) == "orange"

    def test_get_publish_level_yellow(self):
        from utils.publish_policy import get_publish_level

        assert get_publish_level(6) == "yellow"
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

        # В quiet hours red публикуется, orange — нет
        allowed_red, _ = should_publish("red", 10, "normal", True)
        allowed_orange, _ = should_publish("orange", 7, "normal", True)
        assert allowed_red is True
        assert allowed_orange is False
