"""
Тесты для P2-003: Автоматический winner selection (Multi-Armed Bandit).

Покрывают:
- get_winner_variant() — определение winner по стат. значимости
- assign_variant() — 80/20 распределение при наличии winner
- reset_winner() — сброс состояния
- get_winner_status_text() — текстовый статус
- Кеширование winner в БД
"""

import pytest

from storage.ab_testing import (
    AB_VARIANTS,
    EXPLORATION_TRAFFIC_SHARE,
    WINNER_TRAFFIC_SHARE,
    ABTestingManager,
)


class TestWinnerDetection:
    """Тесты определения winner на основе статистики."""

    def test_no_data_returns_none(self):
        manager = ABTestingManager(db_path=":memory:")
        assert manager.get_winner_variant(min_days=7, confidence=0.95) is None

    def test_insufficient_control_returns_none(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(50):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        assert manager.get_winner_variant(min_days=7, confidence=0.95) is None

    def test_no_significant_winner_returns_none(self):
        manager = ABTestingManager(db_path=":memory:")
        # Control: 200 показов, 10 реакций → CTR 5%
        for i in range(200):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(10):
            manager.record_reaction("control", "like")

        # Treatment: 200 показов, 11 реакций → CTR 5.5% (не значимо)
        for i in range(200):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        for _ in range(11):
            manager.record_reaction("no_closer", "like")

        winner = manager.get_winner_variant(min_days=7, confidence=0.95)
        assert winner is None

    def test_significant_winner_detected(self):
        manager = ABTestingManager(db_path=":memory:")
        # Control: 1000 показов, 50 реакций → CTR 5%
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")

        # Treatment: 1000 показов, 100 реакций → CTR 10% (значимо лучше)
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        winner = manager.get_winner_variant(min_days=7, confidence=0.95)
        assert winner is not None
        assert winner["variant"] == "no_closer"
        assert winner["name"] == "Без вопроса"
        assert winner["cached"] is False

    def test_winner_caching(self):
        manager = ABTestingManager(db_path=":memory:")
        # Control
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")

        # Treatment
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        # Первый вызов — определяет и кеширует
        w1 = manager.get_winner_variant(min_days=7, confidence=0.95)
        assert w1["cached"] is False

        # Второй вызов — берёт из кэша
        w2 = manager.get_winner_variant(min_days=7, confidence=0.95)
        assert w2["cached"] is True
        assert w2["variant"] == w1["variant"]

    def test_treatment_worse_not_selected(self):
        manager = ABTestingManager(db_path=":memory:")
        # Control: 1000 показов, 100 реакций → CTR 10%
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(100):
            manager.record_reaction("control", "like")

        # Treatment: 1000 показов, 50 реакций → CTR 5% (хуже)
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(50):
            manager.record_reaction("no_closer", "like")

        winner = manager.get_winner_variant(min_days=7, confidence=0.95)
        assert winner is None  # treatment хуже, не winner


class TestMABAssignment:
    """Тесты 80/20 распределения при наличии winner."""

    def test_uniform_without_winner(self):
        manager = ABTestingManager(db_path=":memory:")
        variants = {v: 0 for v in AB_VARIANTS}
        for i in range(400):
            v = manager.assign_variant(f"https://example.com/{i}")
            variants[v] += 1
        # Без winner — равномерное распределение (~25% каждый)
        for v, count in variants.items():
            assert count > 50, f"{v} имеет только {count} назначений"

    def test_winner_gets_majority_traffic(self):
        manager = ABTestingManager(db_path=":memory:")
        # Настраиваем winner
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        manager.get_winner_variant(min_days=7, confidence=0.95)

        # Собираем статистику назначений
        winner_count = 0
        total = 1000
        for i in range(total):
            v = manager.assign_variant(f"https://new.com/{i}")
            if v == "no_closer":
                winner_count += 1

        # Winner должен получать ~80% трафика (допуск ±10%)
        share = winner_count / total
        assert share >= 0.70, f"Winner получает только {share:.1%} трафика"
        assert share <= 0.90, f"Winner получает слишком много {share:.1%} трафика"

    def test_exploration_still_happens(self):
        manager = ABTestingManager(db_path=":memory:")
        # Настраиваем winner
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        manager.get_winner_variant(min_days=7, confidence=0.95)

        # Проверяем, что exploration варианты всё ещё назначаются
        seen = set()
        for i in range(500):
            v = manager.assign_variant(f"https://new.com/{i}")
            seen.add(v)

        # Должны видеть не только winner
        assert len(seen) > 1, "Exploration не работает — только winner назначается"

    def test_deterministic_with_same_url(self):
        manager = ABTestingManager(db_path=":memory:")
        # Настраиваем winner
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        manager.get_winner_variant(min_days=7, confidence=0.95)

        # Один и тот же URL всегда получает один и тот же вариант
        url = "https://example.com/article/123"
        v1 = manager.assign_variant(url)
        v2 = manager.assign_variant(url)
        v3 = manager.assign_variant(url)
        assert v1 == v2 == v3


class TestResetWinner:
    """Тесты сброса winner state."""

    def test_reset_without_winner(self):
        manager = ABTestingManager(db_path=":memory:")
        assert manager.reset_winner() is False

    def test_reset_with_winner(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        manager.get_winner_variant(min_days=7, confidence=0.95)
        assert manager.reset_winner() is True

        # После сброса winner больше нет
        assert manager._get_cached_winner() is None

        # Распределение снова равномерное
        variants = {v: 0 for v in AB_VARIANTS}
        for i in range(400):
            v = manager.assign_variant(f"https://example.com/{i}")
            variants[v] += 1
        for v, count in variants.items():
            assert count > 50, f"{v} имеет только {count} назначений после reset"


class TestWinnerStatusText:
    """Тесты текстового статуса winner."""

    def test_status_no_data(self):
        manager = ABTestingManager(db_path=":memory:")
        text = manager.get_winner_status_text()
        assert "Нет данных" in text

    def test_status_collecting(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(50):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        text = manager.get_winner_status_text()
        assert "Сбор данных" in text or "недостаточно" in text.lower()

    def test_status_no_winner(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(200):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for i in range(200):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        text = manager.get_winner_status_text()
        assert "нет стат" in text.lower() or "➖" in text

    def test_status_with_winner(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(100):
            manager.record_reaction("no_closer", "like")

        manager.get_winner_variant(min_days=7, confidence=0.95)
        text = manager.get_winner_status_text()
        assert "Winner" in text or "🏆" in text
        assert "80%" in text or "20%" in text
