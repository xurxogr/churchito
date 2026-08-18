"""Tests for the helpers behind the moderator accept/reject actions."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.handlers.flow import (
    RoleChanges,
    apply_role_changes,
    approval_confirmation,
    approval_role_changes,
    previous_statuses,
)


def _guild(roles: dict[int, MagicMock] | None = None) -> MagicMock:
    """Build a guild mock resolving roles from a dict.

    Args:
        roles (dict[int, MagicMock] | None): Roles by ID.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock(spec=discord.Guild)
    guild.name = "Guild"
    guild.get_role.side_effect = lambda role_id: (roles or {}).get(role_id)
    return guild


def _role(role_id: int, name: str) -> MagicMock:
    """Build a role mock.

    Args:
        role_id (int): Role ID.
        name (str): Role name.

    Returns:
        MagicMock: Role mock.
    """
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    return role


class TestPreviousStatuses:
    """Status texts the mod message may show before a moderator decision."""

    def test_returns_ready_pending_and_auto_rejected(self) -> None:
        """Ready-for-approval, pending review and auto-rejected are all included."""
        config = {
            ConfigKey.STATUS_PENDING_REVIEW: "pending!",
            ConfigKey.STATUS_READY_FOR_APPROVAL: "ready {roles}",
            ConfigKey.STATUS_REJECTED: "rejected by {moderator}: {reason}",
        }
        request = MagicMock(rejection_reason="Wrong shard")

        statuses = previous_statuses(config=config, guild=_guild(), request=request)

        assert statuses == ["ready moderators", "pending!", "rejected by Auto: Wrong shard"]

    def test_defaults_when_not_configured(self) -> None:
        """Pending review falls back to a default and a missing reason is empty."""
        config = {ConfigKey.STATUS_REJECTED: "rejected {reason}"}
        request = MagicMock(rejection_reason=None)

        statuses = previous_statuses(config=config, guild=_guild(), request=request)

        assert statuses[1] == "⏳ Pending review"
        assert statuses[2] == "rejected "


class TestApprovalRoleChanges:
    """Role changes and DM template per verification type."""

    def test_regular(self) -> None:
        """Regular verifications use the regular role lists and message."""
        config = {
            ConfigKey.REGULAR_ROLES_ADD: [1, 2],
            ConfigKey.REGULAR_ROLES_REMOVE: [3],
            ConfigKey.ALLY_ROLES_ADD: [9],
        }

        changes = approval_role_changes(config=config, verification_type=VerificationType.REGULAR)

        assert changes == RoleChanges(
            add=[1, 2], remove=[3], message_key=ConfigKey.APPROVAL_MESSAGE_REGULAR
        )

    def test_ally_and_missing_lists(self) -> None:
        """Ally verifications use the ally lists; missing lists are empty."""
        changes = approval_role_changes(
            config={ConfigKey.ALLY_ROLES_ADD: [9]}, verification_type="ally"
        )

        assert changes == RoleChanges(
            add=[9], remove=[], message_key=ConfigKey.APPROVAL_MESSAGE_ALLY
        )


class TestApprovalConfirmation:
    """Moderator confirmation with an optional role warning."""

    def test_without_failures_returns_confirmation(self) -> None:
        """No failed roles → plain confirmation."""
        assert approval_confirmation(confirmation="Done.", failed_roles=[]) == "Done."

    def test_with_failures_appends_warning(self) -> None:
        """Failed roles are listed in a warning after the confirmation."""
        text = approval_confirmation(
            confirmation="Done.", failed_roles=["@Member (add)", "@Guest (remove)"]
        )

        assert text.startswith("Done.\n\n")
        assert "@Member (add), @Guest (remove)" in text
        assert "Manage Roles" in text


class TestApplyRoleChanges:
    """Granting/revoking roles on the approved member."""

    async def test_adds_and_removes_roles(self) -> None:
        """Configured roles are added and removed; nothing fails."""
        add_role, remove_role = _role(1, "Member"), _role(2, "Guest")
        guild = _guild({1: add_role, 2: remove_role})
        member = MagicMock(spec=discord.Member)
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        changes = RoleChanges(add=[1], remove=[2], message_key=ConfigKey.APPROVAL_MESSAGE_REGULAR)

        failed = await apply_role_changes(guild=guild, member=member, changes=changes)

        assert failed == []
        member.add_roles.assert_awaited_once_with(add_role)
        member.remove_roles.assert_awaited_once_with(remove_role)

    async def test_missing_role_is_skipped(self) -> None:
        """Roles that no longer exist are skipped without failing."""
        member = MagicMock(spec=discord.Member)
        member.add_roles = AsyncMock()
        changes = RoleChanges(add=[404], remove=[], message_key=ConfigKey.APPROVAL_MESSAGE_REGULAR)

        failed = await apply_role_changes(guild=_guild(), member=member, changes=changes)

        assert failed == []
        member.add_roles.assert_not_awaited()

    async def test_forbidden_is_reported(self) -> None:
        """Forbidden role changes are reported with the attempted action."""
        guild = _guild({1: _role(1, "Member"), 2: _role(2, "Guest")})
        member = MagicMock(spec=discord.Member)
        forbidden = discord.Forbidden(MagicMock(status=403), "nope")
        member.add_roles = AsyncMock(side_effect=forbidden)
        member.remove_roles = AsyncMock(side_effect=forbidden)
        changes = RoleChanges(add=[1], remove=[2], message_key=ConfigKey.APPROVAL_MESSAGE_REGULAR)

        failed = await apply_role_changes(guild=guild, member=member, changes=changes)

        assert failed == ["@Member (add)", "@Guest (remove)"]


@pytest.mark.parametrize("verification_type", [VerificationType.REGULAR, "regular"])
def test_approval_role_changes_accepts_str_or_enum(verification_type: str) -> None:
    """The stored (str) type and the enum both select the regular lists."""
    changes = approval_role_changes(
        config={ConfigKey.REGULAR_ROLES_ADD: [1]}, verification_type=verification_type
    )

    assert changes.add == [1]
