"""
Tests for P3-004: Automatic world leaders context updater.
"""

import pytest

from ai_core.leaders_updater import (
    WIKI_PAGES,
    _extract_incumbent,
    apply_updates,
    maybe_update_leaders,
)
from ai_core.world_leaders_context import ALL_LEADERS


class TestExtractIncumbent:
    def test_wiki_link_format(self):
        text = "| incumbent = [[Donald Trump]]\n| term_start ="
        assert _extract_incumbent(text) == "Donald Trump"

    def test_plain_text_format(self):
        text = "| incumbent = Vladimir Putin\n| term_start ="
        assert _extract_incumbent(text) == "Vladimir Putin"

    def test_with_display_name(self):
        text = "| incumbent = [[Joe Biden|Biden, Joe]]\n| term_start ="
        assert _extract_incumbent(text) == "Joe Biden"

    def test_no_match(self):
        text = "| president = Someone\n| term_start ="
        assert _extract_incumbent(text) is None

    def test_empty_text(self):
        assert _extract_incumbent("") is None


class TestApplyUpdates:
    def test_apply_valid_update(self):
        # Use a different name to ensure change happens
        updates = {"USA": {"president": "Test Name For Update"}}
        changed = apply_updates(updates)
        assert changed is True
        assert ALL_LEADERS["USA"]["president"]["name_en"] == "Test Name For Update"
        # Restore original
        ALL_LEADERS["USA"]["president"]["name_en"] = "Donald Trump"

    def test_no_change_for_same_name(self):
        current_name = ALL_LEADERS["USA"]["president"]["name_en"]
        updates = {"USA": {"president": current_name}}
        changed = apply_updates(updates)
        assert changed is False

    def test_unknown_country_ignored(self):
        updates = {"UnknownCountry": {"president": "Someone"}}
        changed = apply_updates(updates)
        assert changed is False

    def test_unknown_position_ignored(self):
        updates = {"USA": {"unknown_position": "Someone"}}
        changed = apply_updates(updates)
        assert changed is False


class TestWikiPagesConfig:
    def test_all_pages_have_valid_format(self):
        for (country, position), (page, field) in WIKI_PAGES.items():
            assert page, f"Empty page for {country}/{position}"
            assert field, f"Empty field for {country}/{position}"
            assert " " not in page, f"Page should use underscores: {page}"


class TestMaybeUpdateLeaders:
    @pytest.mark.asyncio
    async def test_force_update(self):
        """Force=True должен выполнить обновление."""
        result = await maybe_update_leaders(force=True)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_skip_if_fresh(self):
        """Если данные свежие (только что обновлены), skip."""
        # Сначала обновляем
        await maybe_update_leaders(force=True)
        # Сразу снова — должно skip
        result = await maybe_update_leaders(force=False)
        assert result is False
