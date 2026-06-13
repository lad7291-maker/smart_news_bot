"""
Тесты для системы пользовательских реакций.
P1-001: Система пользовательских реакций (👍/👎).
"""

from datetime import datetime, timedelta

import pytest

from storage.reactions import ReactionsManager


class TestReactionsManager:
    def test_map_message_to_article(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        ok = mgr.map_message_to_article(
            message_id=123,
            article_link="https://example.com/news/1",
            article_title="Test News",
            source_tag="TestSource",
            score=8,
        )
        assert ok is True
        mgr.close()

    def test_add_and_get_reaction(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        mgr.map_message_to_article(100, "https://example.com/1", "News 1", "Src", 5)

        stats = mgr.add_reaction(100, "user_1", "like")
        assert stats["action"] == "added"
        assert stats["like"] == 1

        # Повторный like — toggle off
        stats = mgr.add_reaction(100, "user_1", "like")
        assert stats["action"] == "removed"
        assert stats["like"] == 0
        mgr.close()

    def test_opposite_reaction_replaces(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        mgr.map_message_to_article(101, "https://example.com/2", "News 2", "Src", 5)

        mgr.add_reaction(101, "user_1", "like")
        stats = mgr.add_reaction(101, "user_1", "dislike")

        # like должен быть удалён, dislike добавлен
        assert stats["like"] == 0
        assert stats["dislike"] == 1
        mgr.close()

    def test_multiple_users(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        mgr.map_message_to_article(102, "https://example.com/3", "News 3", "Src", 5)

        mgr.add_reaction(102, "user_1", "like")
        mgr.add_reaction(102, "user_2", "like")
        mgr.add_reaction(102, "user_3", "dislike")

        stats = mgr.get_message_reactions(102)
        assert stats["like"] == 2
        assert stats["dislike"] == 1
        mgr.close()

    def test_save_reaction(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        mgr.map_message_to_article(103, "https://example.com/4", "News 4", "Src", 5)

        stats = mgr.add_reaction(103, "user_1", "save")
        assert stats["action"] == "added"
        assert stats["save"] == 1
        mgr.close()

    def test_invalid_reaction_type(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        result = mgr.add_reaction(100, "user_1", "invalid")
        assert "error" in result
        mgr.close()

    def test_article_score_boost(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        link = "https://example.com/boost"
        mgr.map_message_to_article(200, link, "Boost News", "Src", 5)

        # 2 likes = +1.0, 1 dislike = -0.3, 1 save = +0.2
        mgr.add_reaction(200, "user_1", "like")
        mgr.add_reaction(200, "user_2", "like")
        mgr.add_reaction(200, "user_3", "dislike")
        mgr.add_reaction(200, "user_4", "save")

        boost = mgr.get_article_score_boost(link)
        expected = 2 * 0.5 + 1 * (-0.3) + 1 * 0.2
        assert abs(boost - expected) < 0.01
        mgr.close()

    def test_top_articles(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        for i in range(3):
            mgr.map_message_to_article(300 + i, f"https://example.com/top{i}", f"Top {i}", "Src", 5)

        # Статья 0: 3 likes
        for u in range(3):
            mgr.add_reaction(300, f"user_{u}", "like")

        # Статья 1: 1 like, 1 dislike
        mgr.add_reaction(301, "user_a", "like")
        mgr.add_reaction(301, "user_b", "dislike")

        # Статья 2: 1 save
        mgr.add_reaction(302, "user_x", "save")

        top = mgr.get_top_articles(days=1, limit=5)
        assert len(top) == 3
        # Статья 0 должна быть первой (3 likes)
        assert top[0]["article_link"] == "https://example.com/top0"
        assert top[0]["likes"] == 3
        mgr.close()

    def test_user_reaction_summary(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        mgr.map_message_to_article(400, "https://example.com/u", "User News", "Src", 5)
        mgr.add_reaction(400, "alice", "like")
        mgr.add_reaction(400, "alice", "save")

        summary = mgr.get_user_reaction_summary("alice", days=1)
        assert summary["like"] == 1
        assert summary["save"] == 1
        assert summary["total"] == 2
        mgr.close()

    def test_empty_reactions(self, tmp_db_path):
        mgr = ReactionsManager(db_path=tmp_db_path)
        stats = mgr.get_message_reactions(999)
        assert stats == {"like": 0, "dislike": 0, "save": 0}

        top = mgr.get_top_articles(days=1, limit=5)
        assert top == []
        mgr.close()
