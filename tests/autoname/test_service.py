"""Tests for autoname service (pure functions)."""

from typing import Any

from discord_bot.autoname.service import (
    build_nickname,
    build_tag_pattern,
    compute_nickname,
    extract_base_name,
    find_matching_value,
)

DEFAULT_FORMAT = "[ABC | {tag}]"


class TestBuildTagPattern:
    """Tests for build_tag_pattern."""

    def test_simple_format(self) -> None:
        """Simple pattern should match correctly."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        assert pattern.match("[ABC | CAP] Xurxo")
        assert pattern.match("★[ABC | SGT] Juan")

    def test_does_not_match_different_format(self) -> None:
        """Should not match different format."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        assert not pattern.match("[XYZ | CAP] Xurxo")
        assert not pattern.match("[OTHER] Name")

    def test_extracts_base_name(self) -> None:
        """Should extract base name correctly."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        match = pattern.match("[ABC | CAP] Xurxo")
        assert match is not None
        assert match.group(1) == "Xurxo"

    def test_extracts_with_prefix(self) -> None:
        """Should extract name even with prefix."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        match = pattern.match("★[ABC | CAP] Xurxo")
        assert match is not None
        assert match.group(1) == "Xurxo"

    def test_special_chars_escaped(self) -> None:
        """Special characters should be escaped."""
        pattern = build_tag_pattern("[A.B | {tag}]")
        assert pattern.match("[A.B | CAP] Name")
        assert not pattern.match("[AXB | CAP] Name")  # . should not match X


class TestExtractBaseName:
    """Tests for extract_base_name."""

    def test_simple_name(self) -> None:
        """Name without tags should be returned as is."""
        result = extract_base_name(display_name="Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_matching_tag(self) -> None:
        """Name with tag matching format should be cleaned."""
        result = extract_base_name(display_name="[ABC | CAP] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_prefix_and_matching_tag(self) -> None:
        """Name with prefix and matching tag should be cleaned."""
        result = extract_base_name(display_name="★[ABC | CAP] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_different_tag_uses_fallback(self) -> None:
        """Tag with different format should be cleaned via generic fallback."""
        # [XYZ | ...] does not match [ABC | ...] but fallback cleans it
        result = extract_base_name(display_name="[XYZ | OLD] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_whitespace_handling(self) -> None:
        """Extra whitespace should be handled correctly."""
        result = extract_base_name(display_name="  [ABC | SGT] Juan  ", tag_format=DEFAULT_FORMAT)
        assert result == "Juan"

    def test_name_with_spaces(self) -> None:
        """Names with spaces should be preserved."""
        result = extract_base_name(
            display_name="[ABC | TAG] Juan Carlos", tag_format=DEFAULT_FORMAT
        )
        assert result == "Juan Carlos"

    def test_format_change_cleans_old_format(self) -> None:
        """When format changes, old one should be cleaned via fallback."""
        old_name = "★[OLD | CAP] Xurxo"
        new_format = "[NEW | {tag}]"
        # Tag [OLD | CAP] does not match [NEW | ...] but fallback cleans it
        result = extract_base_name(display_name=old_name, tag_format=new_format)
        assert result == "Xurxo"

    def test_multiword_name_without_tag_preserved(self) -> None:
        """Multi-word names without tags should be fully preserved."""
        # "Karl Fisburne" should not become "Fisburne"
        result = extract_base_name(display_name="Karl Fisburne", tag_format=DEFAULT_FORMAT)
        assert result == "Karl Fisburne"

    def test_short_first_word_preserved(self) -> None:
        """Short names at the start should not be confused with prefixes."""
        result1 = extract_base_name(display_name="Ana Garcia", tag_format=DEFAULT_FORMAT)
        result2 = extract_base_name(display_name="El Jefe", tag_format=DEFAULT_FORMAT)
        assert result1 == "Ana Garcia"
        assert result2 == "El Jefe"

    def test_strips_known_prefix_without_tag(self) -> None:
        """Should remove known prefix when there is no tag."""
        result = extract_base_name(
            display_name="★ Xurxo",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "Xurxo"

    def test_strips_different_known_prefix(self) -> None:
        """Should remove any known prefix."""
        result = extract_base_name(
            display_name="◈ Juan",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "Juan"

    def test_does_not_strip_unknown_prefix(self) -> None:
        """Should not remove unconfigured prefixes."""
        result = extract_base_name(
            display_name="♦ Pedro",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "♦ Pedro"

    def test_strips_prefix_and_tag_together(self) -> None:
        """Should remove prefix and tag when both are present."""
        result = extract_base_name(
            display_name="★[ABC | CAP] Xurxo",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★"],
        )
        assert result == "Xurxo"


class TestFindMatchingValue:
    """Tests for find_matching_value."""

    def test_first_match_wins(self) -> None:
        """First matching role in the list should win."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200, 100]  # Has both roles

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "CAP"  # CAP is first in config

    def test_no_matching_role(self) -> None:
        """Without matching role should return None."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
        ]
        member_role_ids = [200, 300]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result is None

    def test_empty_roles_config(self) -> None:
        """Empty config should return None."""
        result = find_matching_value(member_role_ids=[100, 200], roles_config=[], value_key="tag")
        assert result is None

    def test_empty_member_roles(self) -> None:
        """Member without roles should return None."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        result = find_matching_value(member_role_ids=[], roles_config=tags_config, value_key="tag")
        assert result is None

    def test_role_id_as_string_in_config(self) -> None:
        """role_id can come as string from form (Discord snowflakes)."""
        # Web form saves role_id as string to avoid JS precision loss
        tags_config = [
            {"role_id": "484072731344764932", "tag": "CAP"},
        ]
        member_role_ids = [484072731344764932]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )
        assert result == "CAP"

    def test_role_id_as_int_in_config(self) -> None:
        """role_id as int also works (compatibility)."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
        ]
        member_role_ids = [100]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )
        assert result == "CAP"

    def test_missing_role_id_skipped(self) -> None:
        """Config without role_id should be skipped."""
        tags_config: list[dict[str, Any]] = [
            {"tag": "CAP"},  # Without role_id
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"

    def test_invalid_role_id_skipped(self) -> None:
        """Non-numeric role_id should be skipped."""
        tags_config: list[dict[str, Any]] = [
            {"role_id": "invalid", "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"

    def test_none_role_id_skipped(self) -> None:
        """None role_id should be skipped."""
        tags_config: list[dict[str, Any]] = [
            {"role_id": None, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"


class TestBuildNickname:
    """Tests for build_nickname."""

    def test_full_nickname(self) -> None:
        """Complete nickname with prefix, tag and name."""
        result = build_nickname(base_name="Xurxo", tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT)
        assert result == "★[ABC | CAP] Xurxo"

    def test_no_prefix(self) -> None:
        """Nickname without prefix."""
        result = build_nickname(base_name="Xurxo", tag="CAP", prefix="", tag_format=DEFAULT_FORMAT)
        assert result == "[ABC | CAP] Xurxo"

    def test_no_tag(self) -> None:
        """Nickname without tag (only name)."""
        result = build_nickname(base_name="Xurxo", tag="", prefix="", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_custom_tag_format(self) -> None:
        """Custom tag format."""
        result = build_nickname(base_name="Xurxo", tag="LEADER", prefix="◈", tag_format="[{tag}]")
        assert result == "◈[LEADER] Xurxo"

    def test_truncation_long_name(self) -> None:
        """Long names should be truncated to 32 characters."""
        long_name = "A" * 40
        result = build_nickname(
            base_name=long_name, tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT
        )
        assert len(result) <= 32

    def test_truncation_preserves_tag(self) -> None:
        """Tag should be preserved and name truncated."""
        long_name = "A" * 30
        result = build_nickname(
            base_name=long_name, tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT
        )

        assert len(result) <= 32
        assert "[ABC | CAP]" in result
        assert "★" in result

    def test_very_long_tag_uses_name_only(self) -> None:
        """If tag is very long, use only truncated name."""
        result = build_nickname(
            base_name="Xurxo",
            tag="CAP",
            prefix="★",
            tag_format="[" + "X" * 40 + " | {tag}]",
        )
        assert len(result) <= 32

    def test_prefix_only_with_empty_tag_format(self) -> None:
        """Prefix with format that results empty when tag is empty."""
        # tag_format="{tag}" with tag="" results in formatted_tag=""
        result = build_nickname(base_name="Xurxo", tag="", prefix="★", tag_format="{tag}")
        assert result == "★ Xurxo"

    def test_truncation_long_name_without_tag(self) -> None:
        """Long name without tag or prefix should be truncated."""
        long_name = "A" * 40
        result = build_nickname(base_name=long_name, tag="", prefix="", tag_format=DEFAULT_FORMAT)
        assert len(result) == 32
        assert result == "A" * 32


class TestComputeNickname:
    """Tests for compute_nickname."""

    def test_computes_new_nickname_with_tag_and_prefix(self) -> None:
        """Should compute new nickname for member with tag and prefix."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "★[ABC | CAP] Xurxo"

    def test_computes_nickname_with_only_tag(self) -> None:
        """Should compute nickname with only tag, without prefix."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "[ABC | CAP] Xurxo"

    def test_computes_nickname_with_only_prefix(self) -> None:
        """Should compute nickname with only prefix, without tag format."""
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # Only prefix should be applied, no empty tag format
        assert result == "★ Xurxo"

    def test_no_change_with_only_prefix(self) -> None:
        """Should not re-add prefix if already has correct format."""
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★ Xurxo",
            current_nick="★ Xurxo",
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_no_change_needed(self) -> None:
        """Should return None if no change."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_cleans_tag_when_no_matching_role(self) -> None:
        """Should clean tag if no matching role."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[200],  # Does not have role 100
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "Xurxo"

    def test_returns_none_when_already_clean(self) -> None:
        """Should return None if already clean."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick="Xurxo",
            member_role_ids=[200],
            tags_config=tags_config,
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_updates_tag_on_role_change(self) -> None:
        """Should update tag when role changes."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        prefixes_config = [
            {"role_id": 100, "prefix": "★"},
            {"role_id": 200, "prefix": "◈"},
        ]

        # Had CAP, now only has SGT
        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[200],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "◈[ABC | SGT] Xurxo"

    def test_empty_configs(self) -> None:
        """Empty config should not make changes."""
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_priority_order(self) -> None:
        """First role in config should have priority."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        prefixes_config = [
            {"role_id": 100, "prefix": "★"},
            {"role_id": 200, "prefix": "◈"},
        ]

        # Has both roles, CAP should win (first in config)
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[200, 100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "★[ABC | CAP] Xurxo"

    def test_independent_tag_and_prefix_priority(self) -> None:
        """Tag and prefix are resolved independently."""
        # Role 100 has tag CAP, Role 200 has prefix ◈
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 200, "prefix": "◈"}]

        # User has both roles
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100, 200],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # Should have tag from role 100 and prefix from role 200
        assert result == "◈[ABC | CAP] Xurxo"

    def test_display_name_equals_result(self) -> None:
        """If display_name is already the result, return None."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick=None,  # Nick is None but display_name is already correct
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_format_change_updates_nickname(self) -> None:
        """Format change should update the nickname."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        # User has the old format
        result = compute_nickname(
            display_name="★[OLD | CAP] Xurxo",
            current_nick="★[OLD | CAP] Xurxo",
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format="[NEW | {tag}]",  # New format
        )

        # Should update to new format
        assert result == "★[NEW | CAP] Xurxo"

    def test_preserves_name_not_matching_format(self) -> None:
        """Name with brackets that do not match format should be preserved."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        # User has name with brackets but it is not an autoname tag
        result = compute_nickname(
            display_name="[Cool] Guy",  # Does not match [ABC | ...]
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # The generic fallback will clean [Cool], so the result would be:
        assert result == "★[ABC | CAP] Guy"
