"""Tests for the pure helpers behind handle_verification_start."""

from unittest.mock import MagicMock

import discord

from discord_bot.verification.config import SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.handlers.start import (
    dm_template_key,
    effective_timeout_minutes,
    is_blocked_by_role,
)


def _member(role_ids: list[int]) -> MagicMock:
    """Build a member mock with the given role IDs.

    Args:
        role_ids (list[int]): Role IDs held by the member.

    Returns:
        MagicMock: Member mock.
    """
    member = MagicMock(spec=discord.Member)
    member.roles = [MagicMock(id=rid) for rid in role_ids]
    return member


class TestIsBlockedByRole:
    """Blocking roles prevent starting a verification."""

    def test_member_with_blocking_role_is_blocked(self) -> None:
        """A member holding any blocking role is blocked."""
        assert is_blocked_by_role(user=_member([1, 2]), blocking_roles=[2, 3])

    def test_member_without_blocking_role_is_not_blocked(self) -> None:
        """A member with none of the blocking roles may start."""
        assert not is_blocked_by_role(user=_member([1]), blocking_roles=[2, 3])

    def test_no_blocking_roles_configured(self) -> None:
        """Without configured blocking roles nobody is blocked."""
        assert not is_blocked_by_role(user=_member([1]), blocking_roles=[])

    def test_plain_user_is_never_blocked(self) -> None:
        """A discord.User (no guild roles) cannot be blocked."""
        user = MagicMock(spec=discord.User)

        assert not is_blocked_by_role(user=user, blocking_roles=[1])


class TestEffectiveTimeoutMinutes:
    """Screenshot timeout with a fallback for abandoned verifications."""

    def test_configured_positive_value_is_used(self) -> None:
        """A positive configured timeout is returned as-is."""
        assert effective_timeout_minutes({ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: 15}) == 15

    def test_zero_missing_or_negative_use_fallback(self) -> None:
        """Zero, missing or negative timeouts fall back to the default."""
        assert (
            effective_timeout_minutes({ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: 0})
            == SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
        )
        assert effective_timeout_minutes({}) == SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
        assert (
            effective_timeout_minutes({ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: -5})
            == SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
        )


class TestDmTemplateKey:
    """DM instructions template per verification type."""

    def test_regular_and_ally_templates(self) -> None:
        """Regular uses the standard template, others use the ally one."""
        assert dm_template_key(VerificationType.REGULAR) == ConfigKey.DM_INSTRUCTIONS_MESSAGE
        assert dm_template_key(VerificationType.ALLY) == ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE
