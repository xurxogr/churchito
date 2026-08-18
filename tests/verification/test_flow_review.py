"""Tests for the helpers behind the rejection selector and manual review."""

from unittest.mock import AsyncMock, MagicMock

from discord_bot.verification.enums import ConfigKey, VerificationStatus
from discord_bot.verification.handlers.flow import (
    build_rejection_reasons,
    is_auto_rejected,
    review_refusal,
)


class TestBuildRejectionReasons:
    """Configured rejection reasons offered in the selector."""

    def test_keeps_non_empty_reasons_in_order(self) -> None:
        """Only configured, non-blank reasons are kept, in the canonical order."""
        config = {
            ConfigKey.REJECT_NAME_MISMATCH: "Name mismatch",
            ConfigKey.REJECT_WRONG_CAPTURES: "Wrong captures",
            ConfigKey.REJECT_HAS_REGIMENT: "   ",
            ConfigKey.REJECT_STEAM_PRIVATE: "Steam private",
        }

        assert build_rejection_reasons(config) == [
            "Wrong captures",
            "Name mismatch",
            "Steam private",
        ]

    def test_shard_and_faction_are_substituted(self) -> None:
        """Shard/faction reasons get the expected value filled in."""
        config = {
            ConfigKey.REJECT_WRONG_SHARD: "Wrong shard, expected {shard}",
            ConfigKey.REJECT_WRONG_FACTION: "Wrong faction, expected {faction}",
            ConfigKey.VERIFICATION_SHARD: "Able",
            ConfigKey.VERIFICATION_FACTION: "Colonial",
        }

        assert build_rejection_reasons(config) == [
            "Wrong shard, expected Able",
            "Wrong faction, expected Colonial",
        ]

    def test_shard_and_faction_skipped_without_expected_value(self) -> None:
        """Without a configured shard/faction those reasons are dropped."""
        config = {
            ConfigKey.REJECT_WRONG_SHARD: "Wrong shard {shard}",
            ConfigKey.REJECT_WRONG_FACTION: "Wrong faction {faction}",
            ConfigKey.REJECT_TIME_DIFF: "Too old",
        }

        assert build_rejection_reasons(config) == ["Too old"]


class TestIsAutoRejected:
    """A request is auto-rejected when rejected by the 'Auto' reviewer."""

    def test_auto_rejected(self) -> None:
        """Rejected by Auto → True."""
        request = MagicMock(status=VerificationStatus.REJECTED, reviewed_by_username="Auto")

        assert is_auto_rejected(request)

    def test_rejected_by_moderator_or_not_rejected(self) -> None:
        """Rejected by a human or not rejected at all → False."""
        by_mod = MagicMock(status=VerificationStatus.REJECTED, reviewed_by_username="mod")
        pending = MagicMock(status=VerificationStatus.PENDING_REVIEW, reviewed_by_username="Auto")

        assert not is_auto_rejected(by_mod)
        assert not is_auto_rejected(pending)


class TestReviewRefusal:
    """Reasons a request cannot be sent back to manual review."""

    async def test_not_found_or_other_guild(self) -> None:
        """Missing request or another guild → not-found message."""
        service = MagicMock()
        config = {ConfigKey.REQUEST_NOT_FOUND_MESSAGE: "nope"}
        other = MagicMock(guild_id=999)

        assert (
            await review_refusal(service=service, config=config, guild_id=1, request=None) == "nope"
        )
        assert (
            await review_refusal(service=service, config=config, guild_id=1, request=other)
            == "nope"
        )

    async def test_not_auto_rejected(self) -> None:
        """A request that was not auto-rejected is refused."""
        request = MagicMock(
            guild_id=1, status=VerificationStatus.PENDING_REVIEW, reviewed_by_username=None
        )

        refusal = await review_refusal(service=MagicMock(), config={}, guild_id=1, request=request)

        assert refusal == "This verification was not auto-rejected."

    async def test_not_latest(self) -> None:
        """Only the user's latest verification can be reviewed."""
        request = MagicMock(
            id=10,
            guild_id=1,
            user_id=5,
            status=VerificationStatus.REJECTED,
            reviewed_by_username="Auto",
        )
        service = MagicMock()
        service.get_latest_by_user = AsyncMock(return_value=MagicMock(id=11))

        refusal = await review_refusal(service=service, config={}, guild_id=1, request=request)

        assert refusal == "Only the user's latest verification can be reviewed."
        service.get_latest_by_user.assert_awaited_once_with(guild_id=1, user_id=5)

    async def test_reviewable(self) -> None:
        """An auto-rejected latest request has no refusal."""
        request = MagicMock(
            id=10,
            guild_id=1,
            user_id=5,
            status=VerificationStatus.REJECTED,
            reviewed_by_username="Auto",
        )
        service = MagicMock()
        service.get_latest_by_user = AsyncMock(return_value=request)

        assert await review_refusal(service=service, config={}, guild_id=1, request=request) is None
