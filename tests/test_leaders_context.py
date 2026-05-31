import pytest
from ai_core.world_leaders_context import ALL_LEADERS, get_leaders_context

class TestLeadersContext:
    def test_context_is_not_empty(self):
        ctx = get_leaders_context()
        assert len(ctx) > 100
        assert "Donald Trump" in ctx
        assert "Vladimir Putin" in ctx

    def test_starmer_spelling(self):
        ctx = get_leaders_context()
        assert "Keir Starmer" in ctx, "FEAT-006: Keir Starmer misspelled"
        assert "Kir Starmer" not in ctx, "FEAT-006: Kir Starmer should not appear"

    def test_shmyhal_spelling(self):
        ctx = get_leaders_context()
        assert "Skmyhal" not in ctx, "FEAT-006: Shmyhal misspelled as Skmyhal"

    def test_xi_spelling(self):
        ctx = get_leaders_context()
        assert "Si Tszinpin" not in ctx, "FEAT-006: Xi misspelled as Si Tszinpin"
