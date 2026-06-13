"""
Тесты для rate limiter.
P1-003: Rate limiting на админ-команды.
"""

import time

import pytest

from utils.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_first_call_allowed(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        allowed, retry = rl.is_allowed("user_1", "cmd_post_now", max_calls=3, window_seconds=60)
        assert allowed is True
        assert retry is None
        rl.close()

    def test_calls_within_limit(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        for _ in range(3):
            allowed, _ = rl.is_allowed("user_1", "cmd_stats", max_calls=3, window_seconds=60)
            assert allowed is True
        rl.close()

    def test_call_exceeds_limit(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        for _ in range(3):
            rl.is_allowed("user_1", "cmd_help", max_calls=3, window_seconds=60)

        allowed, retry = rl.is_allowed("user_1", "cmd_help", max_calls=3, window_seconds=60)
        assert allowed is False
        assert retry is not None
        assert retry > 0
        rl.close()

    def test_window_resets_after_period(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        # Исчерпываем лимит
        for _ in range(2):
            rl.is_allowed("user_2", "cmd_test", max_calls=2, window_seconds=1)

        allowed, _ = rl.is_allowed("user_2", "cmd_test", max_calls=2, window_seconds=1)
        assert allowed is False

        # Ждём истечения окна
        time.sleep(1.1)

        allowed, retry = rl.is_allowed("user_2", "cmd_test", max_calls=2, window_seconds=1)
        assert allowed is True
        assert retry is None
        rl.close()

    def test_different_users_independent(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        for _ in range(3):
            rl.is_allowed("user_a", "cmd_post", max_calls=3, window_seconds=60)

        # user_a исчерпал лимит
        allowed, _ = rl.is_allowed("user_a", "cmd_post", max_calls=3, window_seconds=60)
        assert allowed is False

        # user_b может вызывать
        allowed, _ = rl.is_allowed("user_b", "cmd_post", max_calls=3, window_seconds=60)
        assert allowed is True
        rl.close()

    def test_different_commands_independent(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        for _ in range(3):
            rl.is_allowed("user_1", "cmd_a", max_calls=3, window_seconds=60)

        # cmd_a исчерпан
        allowed, _ = rl.is_allowed("user_1", "cmd_a", max_calls=3, window_seconds=60)
        assert allowed is False

        # cmd_b доступен
        allowed, _ = rl.is_allowed("user_1", "cmd_b", max_calls=3, window_seconds=60)
        assert allowed is True
        rl.close()

    def test_reset_clears_limit(self, tmp_db_path):
        rl = RateLimiter(db_path=tmp_db_path)
        for _ in range(3):
            rl.is_allowed("user_1", "cmd_x", max_calls=3, window_seconds=60)

        allowed, _ = rl.is_allowed("user_1", "cmd_x", max_calls=3, window_seconds=60)
        assert allowed is False

        rl.reset("user_1", "cmd_x")

        allowed, _ = rl.is_allowed("user_1", "cmd_x", max_calls=3, window_seconds=60)
        assert allowed is True
        rl.close()

    def test_persistence_across_instances(self, tmp_db_path):
        rl1 = RateLimiter(db_path=tmp_db_path)
        rl1.is_allowed("persist_user", "cmd_y", max_calls=3, window_seconds=60)
        rl1.close()

        rl2 = RateLimiter(db_path=tmp_db_path)
        allowed, _ = rl2.is_allowed("persist_user", "cmd_y", max_calls=3, window_seconds=60)
        assert allowed is True  # второй вызов из 3
        rl2.close()
