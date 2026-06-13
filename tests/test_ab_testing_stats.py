"""
Тесты для P2-002: Статистическая значимость в A/B-тестах.

Покрывают:
- _z_test() — корректность расчёта z-score, p-value, CI
- _significance_flag() — правильность флагов
- get_results() — добавление стат. полей
- get_report_text() — отображение p-value, CI, флагов
- Вариант с n=10 не объявляется победителем
"""

import math

import pytest

from storage.ab_testing import MIN_SAMPLE_SIZE, ABTestingManager, _significance_flag, _z_test


class TestZTest:
    """Тесты двухвыборочного z-test для пропорций."""

    def test_identical_ctr_zero_z(self):
        """Одинаковый CTR → z=0, p=1."""
        z, p, lo, hi = _z_test(5.0, 5.0, 1000, 1000)
        assert abs(z) < 0.001
        assert p > 0.99
        assert abs(lo + hi) < 0.1  # CI симметричен около 0

    def test_large_difference_significant(self):
        """Большая разница при больших n → низкий p-value."""
        z, p, lo, hi = _z_test(5.0, 8.0, 1000, 1000)
        assert z > 2.0
        assert p < 0.05
        assert lo > 0  # treatment лучше

    def test_small_n_not_significant(self):
        """Маленькие выборки → высокий p-value даже при большой разнице."""
        z, p, lo, hi = _z_test(5.0, 15.0, 10, 10)
        assert p > 0.05  # недостаточно данных

    def test_treatment_worse(self):
        """Treatment хуже control → отрицательный z, p < 0.05 при больших n."""
        z, p, lo, hi = _z_test(10.0, 5.0, 2000, 2000)
        assert z < -2.0
        assert p < 0.05
        assert hi < 0  # treatment хуже

    def test_zero_impressions_fallback(self):
        """Нулевые показы → fallback."""
        z, p, lo, hi = _z_test(5.0, 8.0, 0, 100)
        assert p == 1.0

    def test_ci_bounds_reasonable(self):
        """CI должен быть разумным."""
        z, p, lo, hi = _z_test(5.0, 7.0, 500, 500)
        assert lo < hi
        assert lo > -10
        assert hi < 10

    def test_ctr_0_vs_0(self):
        """Нулевые CTR → z=0, p=1."""
        z, p, lo, hi = _z_test(0.0, 0.0, 100, 100)
        assert abs(z) < 0.001
        assert p == 1.0

    def test_ctr_100_vs_100(self):
        """Максимальные CTR → z=0, p=1."""
        z, p, lo, hi = _z_test(100.0, 100.0, 100, 100)
        assert abs(z) < 0.001
        assert p == 1.0


class TestSignificanceFlag:
    """Тесты флагов стат. значимости."""

    def test_low_n_warning(self):
        assert _significance_flag(0.01, 50, 1.0, 3.0) == "⚠️ Недостаточно данных"

    def test_significant_better(self):
        assert _significance_flag(0.01, 200, 0.5, 3.0) == "✅ Стат. значимо лучше"

    def test_significant_worse(self):
        assert _significance_flag(0.01, 200, -3.0, -0.5) == "❌ Стат. значимо хуже"

    def test_significant_uncertain_direction(self):
        """p < 0.05, но CI включает 0 — редкий случай, но возможный."""
        assert _significance_flag(0.01, 200, -1.0, 2.0) == "✅ Стат. значимо (p < 0.05)"

    def test_no_difference(self):
        assert _significance_flag(0.5, 200, -1.0, 1.0) == "➖ Нет различий"

    def test_boundary_p_005(self):
        """p ровно 0.05 → не значимо."""
        assert _significance_flag(0.05, 200, 0.1, 2.0) == "➖ Нет различий"


class TestGetResultsWithStats:
    """Тесты get_results() с добавлением стат. полей."""

    def test_control_has_no_significance(self):
        manager = ABTestingManager(db_path=":memory:")
        # Нужно минимум данных, чтобы control был
        for i in range(110):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        results = manager.get_results(days=1)
        control = next(r for r in results if r["variant"] == "control")
        assert control["significance"] == "—"
        assert control["p_value"] == 1.0

    def test_treatment_with_low_n_warning(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(110):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for i in range(10):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        results = manager.get_results(days=1)
        treatment = next(r for r in results if r["variant"] == "no_closer")
        assert treatment["significance"] == "⚠️ Недостаточно данных"

    def test_treatment_with_large_n_significant(self):
        manager = ABTestingManager(db_path=":memory:")
        # Control: 1000 показов, 50 реакций → CTR 5%
        for i in range(1000):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for _ in range(50):
            manager.record_reaction("control", "like")

        # Treatment: 1000 показов, 80 реакций → CTR 8%
        for i in range(1000):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 1000)
        for _ in range(80):
            manager.record_reaction("no_closer", "like")

        results = manager.get_results(days=1)
        treatment = next(r for r in results if r["variant"] == "no_closer")
        assert treatment["p_value"] < 0.05
        assert treatment["significance"] == "✅ Стат. значимо лучше"
        assert treatment["ci_lower"] > 0

    def test_no_control_data_all_warning(self):
        manager = ABTestingManager(db_path=":memory:")
        results = manager.get_results(days=1)
        for r in results:
            assert r["significance"] == "⚠️ Недостаточно данных"


class TestReportText:
    """Тесты get_report_text() с p-value и CI."""

    def test_report_shows_p_value(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(200):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        manager.record_reaction("control", "like")
        text = manager.get_report_text(days=1)
        assert "p=" in text

    def test_report_shows_ci(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(200):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for i in range(200):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        text = manager.get_report_text(days=1)
        assert "CI95" in text

    def test_small_n_not_declared_winner(self):
        """Вариант с n=10 не объявляется победителем."""
        manager = ABTestingManager(db_path=":memory:")
        for i in range(110):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for i in range(10):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        # Даём treatment 100% CTR, но n=10
        for _ in range(10):
            manager.record_reaction("no_closer", "like")
        text = manager.get_report_text(days=1)
        # Не должно быть 🏆 с no_closer
        assert "🏆 Лучший CTR" not in text or "no_closer" not in text.split("🏆")[-1]
        # Должно быть предупреждение
        assert "недостаточно данных" in text.lower() or "➖" in text or "⚠️" in text

    def test_report_shows_significance_flags(self):
        manager = ABTestingManager(db_path=":memory:")
        for i in range(200):
            manager.record_sent(f"https://a.com/{i}", "T", "control", message_id=i)
        for i in range(200):
            manager.record_sent(f"https://b.com/{i}", "T", "no_closer", message_id=i + 200)
        text = manager.get_report_text(days=1)
        # Должен содержать один из флагов
        assert any(flag in text for flag in ["✅", "⚠️", "➖", "❌"])
