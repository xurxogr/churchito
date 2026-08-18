"""Tests for the reaction panel dashboard form helpers."""

import pytest

from discord_bot.web.panel_forms import MAX_ROLE_MAPPINGS, parse_role_mappings


class TestParseRoleMappingsLimits:
    """The dashboard enforces the same mapping rules as the slash commands."""

    def test_accepts_distinct_emojis(self) -> None:
        """Different unicode and custom emojis are all kept."""
        mappings = parse_role_mappings(
            [
                {"emoji": "👍", "role_id": "1"},
                {"emoji": "👎", "role_id": "2"},
                {"emoji": "party", "emoji_id": "10", "role_id": "3"},
                {"emoji": "party", "emoji_id": "11", "role_id": "4"},
            ]
        )

        assert [m["role_id"] for m in mappings] == [1, 2, 3, 4]

    def test_rejects_a_repeated_unicode_emoji(self) -> None:
        """Only the first mapping of an emoji would ever be reachable."""
        with pytest.raises(ValueError, match="duplicate emoji"):
            parse_role_mappings(
                [{"emoji": "👍", "role_id": "1"}, {"emoji": " 👍 ", "role_id": "2"}]
            )

    def test_rejects_a_repeated_custom_emoji(self) -> None:
        """Custom emojis are compared by ID, not by name."""
        with pytest.raises(ValueError, match="duplicate emoji"):
            parse_role_mappings(
                [
                    {"emoji": "party", "emoji_id": "10", "role_id": "1"},
                    {"emoji": "party_old", "emoji_id": 10, "role_id": "2"},
                ]
            )

    def test_rejects_more_mappings_than_reactions_fit_on_a_message(self) -> None:
        """Discord allows 20 distinct reactions per message."""
        mappings = [{"emoji": chr(0x1F600 + i), "role_id": str(i)} for i in range(21)]

        with pytest.raises(ValueError, match="at most 20"):
            parse_role_mappings(mappings)

        assert len(parse_role_mappings(mappings[:MAX_ROLE_MAPPINGS])) == 20
