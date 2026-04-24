"""Tests for discord_bot/verification/auto_processor.py."""

from typing import Any
from unittest.mock import MagicMock

from discord_bot.verification.auto_processor import (
    calculate_time_diff_days,
    extract_regiment_id,
    extract_regiment_number,
    get_auto_rejectable_failures,
    get_rejection_message,
    is_auto_reject_enabled,
    names_match,
    process_verification,
)
from discord_bot.verification.enums import (
    ConfigKey,
    NameMatchMode,
    RejectType,
    VerificationType,
)
from discord_bot.verification.models import VerificationAPIResponse


class TestCalculateTimeDiffDays:
    """Tests for calculate_time_diff_days."""

    def test_same_day(self) -> None:
        """Test when they are the same day."""
        result = calculate_time_diff_days("268, 07:41", "268, 08:34")
        assert result == 0

    def test_ten_days_diff(self) -> None:
        """Test 10 day difference."""
        result = calculate_time_diff_days("268, 07:41", "278, 08:34")
        assert result == 10

    def test_negative_diff(self) -> None:
        """Test that returns absolute value."""
        result = calculate_time_diff_days("278, 07:41", "268, 08:34")
        assert result == 10

    def test_invalid_format(self) -> None:
        """Test with invalid format returns 0."""
        result = calculate_time_diff_days("invalid", "278, 08:34")
        assert result == 0

    def test_empty_string(self) -> None:
        """Test with empty string returns 0."""
        result = calculate_time_diff_days("", "278, 08:34")
        assert result == 0


class TestNamesMatch:
    """Tests for names_match."""

    def test_exact_match(self) -> None:
        """Test exact match."""
        assert names_match("Player", "Player", NameMatchMode.EXACT) is True

    def test_exact_case_insensitive(self) -> None:
        """Test that it is case insensitive in exact mode."""
        assert names_match("PLAYER", "player", NameMatchMode.EXACT) is True
        assert names_match("Player", "PLAYER", NameMatchMode.EXACT) is True

    def test_exact_with_whitespace(self) -> None:
        """Test that handles whitespace in exact mode."""
        assert names_match("  Player  ", "Player", NameMatchMode.EXACT) is True

    def test_exact_different_names(self) -> None:
        """Test different names in exact mode."""
        assert names_match("Player1", "Player2", NameMatchMode.EXACT) is False

    def test_contains_discord_in_game(self) -> None:
        """Test that Discord name is contained in game name."""
        assert names_match("Player", "Player [TAG]", NameMatchMode.CONTAINS) is True

    def test_contains_game_in_discord(self) -> None:
        """Test that game name is contained in Discord name."""
        assert names_match("[TAG] Player", "Player", NameMatchMode.CONTAINS) is True

    def test_contains_case_insensitive(self) -> None:
        """Test that contains is case insensitive."""
        assert names_match("PLAYER", "player [tag]", NameMatchMode.CONTAINS) is True

    def test_contains_no_match(self) -> None:
        """Test that contains fails when there is no match."""
        assert names_match("Player1", "Player2", NameMatchMode.CONTAINS) is False

    def test_none_mode_always_true(self) -> None:
        """Test that NONE mode always returns True."""
        assert names_match("Player1", "Player2", NameMatchMode.NONE) is True


class TestExtractRegimentId:
    """Tests for extract_regiment_id."""

    def test_standard_format(self) -> None:
        """Test standard format [ID#number] Name."""
        result = extract_regiment_id("[7-HP#8707] 7th Hispanic Platoon")
        assert result == "7-HP#8707"

    def test_different_id_format(self) -> None:
        """Test with another ID format."""
        result = extract_regiment_id("[ABC#1234] Some Regiment Name")
        assert result == "ABC#1234"

    def test_no_hash(self) -> None:
        """Test when there is no # in the content."""
        result = extract_regiment_id("[SOLO] Regiment Name")
        assert result == "SOLO"

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = extract_regiment_id("")
        assert result is None

    def test_no_brackets(self) -> None:
        """Test when there are no brackets."""
        result = extract_regiment_id("SomeRegiment")
        assert result is None

    def test_no_closing_bracket(self) -> None:
        """Test when closing bracket is missing."""
        result = extract_regiment_id("[7-HP#8707 Missing bracket")
        assert result is None

    def test_empty_brackets(self) -> None:
        """Test with empty brackets."""
        result = extract_regiment_id("[] Regiment Name")
        assert result == ""

    def test_complex_id(self) -> None:
        """Test with complex ID."""
        result = extract_regiment_id("[82DK-TF#5555] 82nd Task Force")
        assert result == "82DK-TF#5555"


class TestExtractRegimentNumber:
    """Tests for extract_regiment_number."""

    def test_standard_format(self) -> None:
        """Test extracting number from standard format."""
        result = extract_regiment_number("7-HP#8707")
        assert result == "8707"

    def test_without_hyphen(self) -> None:
        """Test extracting number when OCR misses hyphen."""
        result = extract_regiment_number("7HP#8707")
        assert result == "8707"

    def test_complex_id(self) -> None:
        """Test with complex ID format."""
        result = extract_regiment_number("82DK-TF#5555")
        assert result == "5555"

    def test_no_hash(self) -> None:
        """Test when there is no # in the ID."""
        result = extract_regiment_number("SOLO")
        assert result is None

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = extract_regiment_number("")
        assert result is None

    def test_none_input(self) -> None:
        """Test with None-like input."""
        result = extract_regiment_number("")
        assert result is None

    def test_multiple_hashes(self) -> None:
        """Test with multiple # characters (uses last one)."""
        result = extract_regiment_number("A#B#1234")
        assert result == "1234"


class TestProcessVerification:
    """Tests for process_verification."""

    def _create_request(
        self, verification_type: VerificationType = VerificationType.REGULAR
    ) -> MagicMock:
        """Create a mock VerificationRequest."""
        request = MagicMock()
        request.verification_type = verification_type
        return request

    def _create_api_response(
        self,
        name: str = "TestPlayer",
        regiment: str = "",
        faction: str = "colonial",
        shard: str = "ABLE",
        ingame_time: str = "268, 07:41",
        current_ingame_time: str = "268, 08:34",
    ) -> VerificationAPIResponse:
        """Create an API response."""
        return VerificationAPIResponse(
            name=name,
            level=25,
            regiment=regiment,
            faction=faction,
            shard=shard,
            ingame_time=ingame_time,
            war_number=100,
            current_ingame_time=current_ingame_time,
        )

    def test_all_checks_pass(self) -> None:
        """Test that approves when everything is correct."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.NONE,
            ConfigKey.VERIFICATION_TIME_DIFF: 0,
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_name_mismatch_exact_rejected(self) -> None:
        """Test rejection for different name in exact mode."""
        request = self._create_request()
        api_response = self._create_api_response(name="DifferentName")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.EXACT,
            ConfigKey.REJECT_NAME_MISMATCH: "Name does not match",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.NAME_MISMATCH in failures
        # Verify message can be retrieved
        message = get_rejection_message(config=config, reason=RejectType.NAME_MISMATCH)
        assert message == "Name does not match"

    def test_name_match_contains_approved(self) -> None:
        """Test approval when name is contained."""
        request = self._create_request()
        api_response = self._create_api_response(name="TestPlayer [TAG]")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.CONTAINS,
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_name_match_contains_rejected(self) -> None:
        """Test rejection when name is not contained."""
        request = self._create_request()
        api_response = self._create_api_response(name="CompletelyDifferent")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.CONTAINS,
            ConfigKey.REJECT_NAME_MISMATCH: "Name does not match",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.NAME_MISMATCH in failures

    def test_has_regiment_rejected_for_regular(self) -> None:
        """Test rejection for having regiment in regular verification."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="SomeRegiment")
        config: dict[str, Any] = {
            ConfigKey.REJECT_HAS_REGIMENT: "Has regiment",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.HAS_REGIMENT in failures
        message = get_rejection_message(config=config, reason=RejectType.HAS_REGIMENT)
        assert message == "Has regiment"

    def test_has_regiment_allowed_for_ally(self) -> None:
        """Test that having regiment is allowed for allies."""
        request = self._create_request(verification_type=VerificationType.ALLY)
        api_response = self._create_api_response(regiment="SomeRegiment")
        config: dict[str, Any] = {}

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_valid_regiment_configured_and_matches(self) -> None:
        """Test approval when regiment matches the valid one."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[7-HP#8707] 7th Hispanic Platoon")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "7-HP#8707",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_valid_regiment_matches_with_ocr_error(self) -> None:
        """Test approval when OCR misses characters but number matches."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        # OCR returns 7HP instead of 7-HP (missing hyphen)
        api_response = self._create_api_response(regiment="[7HP#8707] 7th Hispanic Platoon")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "7-HP#8707",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_valid_regiment_configured_but_different(self) -> None:
        """Test rejection when regiment does not match the valid one."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[OTHER#1234] Other Regiment")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "7-HP#8707",
            ConfigKey.REJECT_HAS_REGIMENT: "Invalid regiment",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.HAS_REGIMENT in failures
        message = get_rejection_message(config=config, reason=RejectType.HAS_REGIMENT)
        assert message == "Invalid regiment"

    def test_valid_regiment_empty_rejects_any_regiment(self) -> None:
        """Test that if there is no valid regiment, rejects any regiment."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[7-HP#8707] 7th Hispanic Platoon")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "",
            ConfigKey.REJECT_HAS_REGIMENT: "Has regiment",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.HAS_REGIMENT in failures

    def test_time_diff_exceeded(self) -> None:
        """Test rejection for excessive time difference."""
        request = self._create_request()
        api_response = self._create_api_response(
            ingame_time="100, 07:41",
            current_ingame_time="200, 08:34",  # 100 days diff
        )
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TIME_DIFF: 30,
            ConfigKey.REJECT_TIME_DIFF: "Old screenshot",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.TIME_DIFF in failures
        message = get_rejection_message(config=config, reason=RejectType.TIME_DIFF)
        assert message == "Old screenshot"

    def test_wrong_shard_rejected(self) -> None:
        """Test rejection for incorrect shard."""
        request = self._create_request()
        api_response = self._create_api_response(shard="CHARLIE")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_SHARD: "ABLE",
            ConfigKey.REJECT_WRONG_SHARD: "Wrong shard, must be {shard}",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.WRONG_SHARD in failures
        # Message formatting with shard placeholder
        message = get_rejection_message(config=config, reason=RejectType.WRONG_SHARD, shard="ABLE")
        assert "ABLE" in message

    def test_wrong_faction_rejected(self) -> None:
        """Test rejection for incorrect faction."""
        request = self._create_request()
        api_response = self._create_api_response(faction="wardens")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.REJECT_WRONG_FACTION: "Wrong faction",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.WRONG_FACTION in failures
        message = get_rejection_message(config=config, reason=RejectType.WRONG_FACTION)
        assert message == "Wrong faction"

    def test_correct_faction_approved(self) -> None:
        """Test approval with correct faction."""
        request = self._create_request()
        api_response = self._create_api_response(faction="colonial")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_faction_case_insensitive(self) -> None:
        """Test that faction comparison is case insensitive."""
        request = self._create_request()
        api_response = self._create_api_response(faction="COLONIAL")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_legacy_boolean_true_match_name(self) -> None:
        """Test compatibility with legacy boolean True for match_name."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: True,  # Legacy boolean
        }

        # Name matches exactly
        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert failures == set()

    def test_legacy_boolean_false_match_name(self) -> None:
        """Test compatibility with legacy boolean False for match_name."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: False,  # Legacy boolean
        }

        # Name does not match but it does not matter because it is disabled
        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="DifferentName",
        )

        assert failures == set()

    def test_multiple_failures(self) -> None:
        """Test that multiple failures are collected."""
        request = self._create_request()
        api_response = self._create_api_response(
            faction="wardens",  # Wrong faction
            shard="CHARLIE",  # Wrong shard
            name="DifferentName",  # Wrong name
            ingame_time="100, 07:41",
            current_ingame_time="200, 08:34",  # 100 days diff
        )
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.VERIFICATION_SHARD: "ABLE",
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.EXACT,
            ConfigKey.VERIFICATION_TIME_DIFF: 30,
        }

        failures = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert RejectType.WRONG_FACTION in failures
        assert RejectType.WRONG_SHARD in failures
        assert RejectType.NAME_MISMATCH in failures
        assert RejectType.TIME_DIFF in failures
        assert len(failures) == 4


class TestIsAutoRejectEnabled:
    """Tests for is_auto_reject_enabled."""

    def test_enabled_by_default(self) -> None:
        """Test that auto-reject is enabled by default when not configured."""
        config: dict[str, Any] = {}

        assert is_auto_reject_enabled(config=config, reason=RejectType.NAME_MISMATCH) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.HAS_REGIMENT) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_SHARD) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_FACTION) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.TIME_DIFF) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.INVALID_SCREENSHOTS) is True

    def test_can_disable_name_mismatch(self) -> None:
        """Test disabling auto-reject for name mismatch."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_NAME_MISMATCH: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.NAME_MISMATCH) is False
        # Others should still be enabled
        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_SHARD) is True

    def test_can_disable_has_regiment(self) -> None:
        """Test disabling auto-reject for regiment check."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_HAS_REGIMENT: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.HAS_REGIMENT) is False

    def test_can_disable_wrong_shard(self) -> None:
        """Test disabling auto-reject for wrong shard."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_WRONG_SHARD: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_SHARD) is False

    def test_can_disable_wrong_faction(self) -> None:
        """Test disabling auto-reject for wrong faction."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_WRONG_FACTION: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_FACTION) is False

    def test_can_disable_time_diff(self) -> None:
        """Test disabling auto-reject for old screenshot."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_TIME_DIFF: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.TIME_DIFF) is False

    def test_can_disable_invalid_screenshots(self) -> None:
        """Test disabling auto-reject for invalid screenshots."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_INVALID_SCREENSHOTS: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.INVALID_SCREENSHOTS) is False

    def test_multiple_disabled(self) -> None:
        """Test disabling multiple auto-reject reasons."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_NAME_MISMATCH: False,
            ConfigKey.AUTO_REJECT_WRONG_SHARD: False,
            ConfigKey.AUTO_REJECT_INVALID_SCREENSHOTS: False,
        }

        assert is_auto_reject_enabled(config=config, reason=RejectType.NAME_MISMATCH) is False
        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_SHARD) is False
        assert is_auto_reject_enabled(config=config, reason=RejectType.INVALID_SCREENSHOTS) is False
        # Others should still be enabled
        assert is_auto_reject_enabled(config=config, reason=RejectType.HAS_REGIMENT) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.WRONG_FACTION) is True
        assert is_auto_reject_enabled(config=config, reason=RejectType.TIME_DIFF) is True


class TestGetAutoRejectableFailures:
    """Tests for get_auto_rejectable_failures."""

    def test_all_failures_auto_rejectable_by_default(self) -> None:
        """Test all failures are auto-rejectable when nothing is disabled."""
        config: dict[str, Any] = {}
        failures = {RejectType.WRONG_FACTION, RejectType.WRONG_SHARD, RejectType.NAME_MISMATCH}

        result = get_auto_rejectable_failures(config=config, failures=failures)

        assert result == failures

    def test_filters_out_disabled_failures(self) -> None:
        """Test that failures with disabled auto-reject are filtered out."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_WRONG_SHARD: False,
        }
        failures = {RejectType.WRONG_FACTION, RejectType.WRONG_SHARD, RejectType.NAME_MISMATCH}

        result = get_auto_rejectable_failures(config=config, failures=failures)

        assert result == {RejectType.WRONG_FACTION, RejectType.NAME_MISMATCH}
        assert RejectType.WRONG_SHARD not in result

    def test_empty_failures_returns_empty(self) -> None:
        """Test empty failures returns empty set."""
        config: dict[str, Any] = {}
        failures: set[RejectType] = set()

        result = get_auto_rejectable_failures(config=config, failures=failures)

        assert result == set()

    def test_all_disabled_returns_empty(self) -> None:
        """Test when all failures have auto-reject disabled."""
        config: dict[str, Any] = {
            ConfigKey.AUTO_REJECT_WRONG_FACTION: False,
            ConfigKey.AUTO_REJECT_WRONG_SHARD: False,
        }
        failures = {RejectType.WRONG_FACTION, RejectType.WRONG_SHARD}

        result = get_auto_rejectable_failures(config=config, failures=failures)

        assert result == set()
