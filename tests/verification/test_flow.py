"""Tests for the helpers behind the moderator accept/reject actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.common.services.database import DatabaseService
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.handlers.flow import (
    ModActionContext,
    RoleChanges,
    _grant_approval,
    _notify_rejection,
    _publish_decision,
    apply_role_changes,
    approval_confirmation,
    approval_role_changes,
    previous_statuses,
)
from discord_bot.verification.service import VerificationService


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


class TestDecisionDmBestEffort:
    """The decision DMs must never abort an accept/reject already applied."""

    def _member(self) -> MagicMock:
        """Build a member mock whose DM fails with an HTTP 400.

        Returns:
            MagicMock: Member mock with a failing ``send``.
        """
        member = MagicMock(spec=discord.Member)
        member.name = "TestUser"
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        member.send = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "Must be 2000 or fewer in length."
            )
        )
        return member

    def _request(self) -> MagicMock:
        """Build a verification request mock.

        Returns:
            MagicMock: Request mock for a regular verification.
        """
        request = MagicMock()
        request.user_id = 654
        request.username = "TestUser"
        request.verification_type = VerificationType.REGULAR.value
        request.rejection_reason = None
        return request

    async def test_approval_dm_http_error_does_not_abort_approval(self) -> None:
        """An oversized approval DM is swallowed after the roles were applied."""
        member = self._member()
        guild = _guild({1: _role(1, "Member")})
        guild.get_member.return_value = member
        config = {ConfigKey.REGULAR_ROLES_ADD: [1]}

        failed_roles = await _grant_approval(guild=guild, config=config, request=self._request())

        assert failed_roles == []
        member.add_roles.assert_awaited_once()
        member.send.assert_awaited_once()

    async def test_rejection_dm_http_error_does_not_abort_rejection(self) -> None:
        """An oversized rejection DM (template + long reason) is swallowed."""
        member = self._member()
        guild = _guild()
        guild.get_member.return_value = member
        config = {ConfigKey.REJECTION_MESSAGE: "Rejected: {reason}"}

        await _notify_rejection(
            guild=guild, config=config, request=self._request(), reason="x" * 500
        )

        member.send.assert_awaited_once()


class TestPublishDecisionPersistsFirst:
    """The decision must be committed before the mod message is updated."""

    async def test_approval_persists_when_mod_message_update_fails(
        self, test_database: DatabaseService
    ) -> None:
        """Test that the approval commits even if the mod message edit fails.

        The verification roles are already granted when the mod message is
        updated, so a rollback would leave a verified member with a pending
        request that a second moderator could still reject.
        """
        async with test_database.session() as session:
            service = VerificationService(session=session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            request_id = request.id

        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        moderator = MagicMock(spec=discord.Member)
        moderator.name = "Mod"
        moderator.display_name = "Mod"

        with (
            patch(
                "discord_bot.verification.handlers.flow.update_mod_message_status",
                new=AsyncMock(side_effect=discord.HTTPException(MagicMock(), "edit failed")),
            ),
            pytest.raises(discord.HTTPException),
        ):
            async with test_database.session() as session:
                service = VerificationService(session=session)
                stored = await service.get_request(request_id)
                assert stored is not None
                await service.approve(
                    request_id=request_id,
                    reviewer_id=789,
                    reviewer_username="Mod",
                    guild_name="Test Guild",
                )
                await _publish_decision(
                    session=session,
                    guild=guild,
                    ctx=ModActionContext(config={}, request=stored, service=service),
                    moderator=moderator,
                    status_key=ConfigKey.STATUS_APPROVED,
                    color=discord.Color.green(),
                    previous=[],
                )

        async with test_database.session() as session:
            service = VerificationService(session=session)
            stored = await service.get_request(request_id)
            assert stored is not None
            assert stored.status == VerificationStatus.APPROVED
