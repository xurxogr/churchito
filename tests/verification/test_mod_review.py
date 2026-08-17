"""Tests for the pure helpers behind update_mod_message_for_review."""

from unittest.mock import MagicMock

from discord_bot.verification.enums import (
    AutoProcessMode,
    ConfigKey,
    NameMatchMode,
    RejectType,
    VerificationType,
)
from discord_bot.verification.handlers.mod_messages import (
    STATUS_DISABLED,
    STATUS_FAILED,
    STATUS_PASSED,
)
from discord_bot.verification.handlers.mod_review import (
    build_check_statuses,
    build_rejection_messages,
    initial_failures,
    resolve_auto_flags,
    summarize_api_result,
)
from discord_bot.verification.models import (
    SteamProfileCheckResult,
    VerificationAPIResponse,
    VerificationAPIResult,
)


def _request(verification_type: VerificationType = VerificationType.REGULAR) -> MagicMock:
    """Build a verification request mock.

    Args:
        verification_type (VerificationType): Request verification type.

    Returns:
        MagicMock: Request mock.
    """
    request = MagicMock()
    request.verification_type = verification_type.value
    return request


class TestSummarizeApiResult:
    """API result → player info / status placeholder."""

    def test_none_result_yields_empty_outcome(self) -> None:
        """Without an API call there is neither player info nor status."""
        outcome = summarize_api_result(api_result=None, config={})

        assert outcome.player_info is None
        assert outcome.api_status == ""

    def test_success_builds_player_info_with_fallbacks(self) -> None:
        """Successful response maps fields, using N/A for empty strings."""
        response = VerificationAPIResponse(name="Neo", level=7, war_number=115)
        result = VerificationAPIResult(success=True, status_code=200, response=response)

        outcome = summarize_api_result(api_result=result, config={})

        assert outcome.player_info == {
            "name": "Neo",
            "regiment": "N/A",
            "level": "7",
            "faction": "N/A",
            "shard": "N/A",
            "time": "N/A",
            "war": "115",
            "war_time": "N/A",
        }
        assert outcome.api_status == ""

    def test_422_uses_wrong_captures_message(self) -> None:
        """A 422 uses the configured wrong-captures message as a warning."""
        result = VerificationAPIResult(success=False, status_code=422)

        outcome = summarize_api_result(
            api_result=result, config={ConfigKey.REJECT_WRONG_CAPTURES: "Bad pics"}
        )

        assert outcome.player_info is None
        assert outcome.api_status == "⚠️ **Bad pics**"

    def test_other_error_reports_api_error(self) -> None:
        """Other failures show an API error line."""
        result = VerificationAPIResult(success=False, status_code=500)

        outcome = summarize_api_result(api_result=result, config={})

        assert outcome.player_info is None
        assert outcome.api_status.startswith("❌ **API Error:**")


class TestInitialFailures:
    """Steam privacy check seeds the failure set."""

    def test_private_profile_adds_steam_private(self) -> None:
        """A successful check that finds a private profile is a failure."""
        check = SteamProfileCheckResult(success=True, is_private=True)

        assert initial_failures(steam_check=check) == {RejectType.STEAM_PRIVATE}

    def test_public_missing_or_inconclusive_yields_no_failures(self) -> None:
        """Public, absent or inconclusive checks add nothing."""
        assert initial_failures(steam_check=None) == set()
        assert initial_failures(steam_check=SteamProfileCheckResult(success=True)) == set()
        assert (
            initial_failures(steam_check=SteamProfileCheckResult(success=False, is_private=True))
            == set()
        )


class TestResolveAutoFlags:
    """Auto-process mode → (auto_reject, auto_approve)."""

    def test_modes_map_to_flags(self) -> None:
        """Each mode enables the matching flags; legacy booleans still work."""
        cases = {
            AutoProcessMode.NONE: (False, False),
            AutoProcessMode.REJECT_ONLY: (True, False),
            AutoProcessMode.APPROVE_ONLY: (False, True),
            AutoProcessMode.BOTH: (True, True),
            True: (True, True),
            False: (False, False),
            None: (False, False),
        }
        for mode, expected in cases.items():
            config = {ConfigKey.VERIFICATION_AUTOMATIC: mode}
            assert (
                resolve_auto_flags(config=config, guild_name="G", steam_check_inconclusive=False)
                == expected
            ), mode

    def test_inconclusive_steam_check_disables_auto_approve(self) -> None:
        """An unverified Steam privacy state never auto-approves."""
        config = {ConfigKey.VERIFICATION_AUTOMATIC: AutoProcessMode.BOTH}

        assert resolve_auto_flags(config=config, guild_name="G", steam_check_inconclusive=True) == (
            True,
            False,
        )


class TestBuildCheckStatuses:
    """Per-check status indicators."""

    def test_no_api_response_disables_every_api_check(self) -> None:
        """Without an API response only the steam check can be enabled."""
        config = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.STEAM_PROFILE_REQUIRED_REGULAR: True,
        }

        statuses = build_check_statuses(
            config=config,
            failures={RejectType.STEAM_PRIVATE},
            request=_request(),
            api_response_exists=False,
        )

        assert statuses == {
            "faction_status": STATUS_DISABLED,
            "shard_status": STATUS_DISABLED,
            "regiment_status": STATUS_DISABLED,
            "name_status": STATUS_DISABLED,
            "time_status": STATUS_DISABLED,
            "steam_status": STATUS_FAILED,
        }

    def test_enabled_checks_pass_or_fail(self) -> None:
        """Configured checks show pass/fail; unconfigured ones stay disabled."""
        config = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.VERIFICATION_SHARD: "ABLE",
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.NONE,
            ConfigKey.VERIFICATION_TIME_DIFF: 30,
        }

        statuses = build_check_statuses(
            config=config,
            failures={RejectType.WRONG_SHARD, RejectType.TIME_DIFF},
            request=_request(VerificationType.ALLY),
            api_response_exists=True,
        )

        assert statuses == {
            "faction_status": STATUS_PASSED,
            "shard_status": STATUS_FAILED,
            "regiment_status": STATUS_DISABLED,
            "name_status": STATUS_DISABLED,
            "time_status": STATUS_FAILED,
            "steam_status": STATUS_DISABLED,
        }

    def test_legacy_boolean_name_match_and_regular_regiment(self) -> None:
        """Legacy True for name matching enables it; regiment check only for REGULAR."""
        config = {ConfigKey.VERIFICATION_MATCH_NAME: True}

        statuses = build_check_statuses(
            config=config,
            failures={RejectType.NAME_MISMATCH, RejectType.HAS_REGIMENT},
            request=_request(VerificationType.REGULAR),
            api_response_exists=True,
        )

        assert statuses["name_status"] == STATUS_FAILED
        assert statuses["regiment_status"] == STATUS_FAILED


class TestBuildRejectionMessages:
    """Rejection messages follow enum order and get shard/faction placeholders."""

    def test_messages_in_enum_order_with_placeholders(self) -> None:
        """Shard and faction messages receive their configured values."""
        config = {
            ConfigKey.VERIFICATION_SHARD: "ABLE",
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.REJECT_WRONG_SHARD: "Shard {shard}",
            ConfigKey.REJECT_WRONG_FACTION: "Faction {faction}",
        }

        messages = build_rejection_messages(
            config=config, failures={RejectType.WRONG_SHARD, RejectType.WRONG_FACTION}
        )

        assert messages == ["Faction colonial", "Shard ABLE"]
