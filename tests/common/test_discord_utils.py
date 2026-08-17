"""Tests for role helpers in discord_bot.common.utils.discord."""

from unittest.mock import MagicMock

import discord

from discord_bot.common.utils import has_any_of_roles, has_any_role


def _member_with_roles(*role_ids: int) -> MagicMock:
    """Build a member mock holding the given role IDs.

    Args:
        *role_ids (int): Role IDs the member has.

    Returns:
        MagicMock: Member mock with ``roles`` populated.
    """
    member = MagicMock(spec=discord.Member)
    roles = []
    for role_id in role_ids:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        roles.append(role)
    member.roles = roles
    return member


class TestHasAnyOfRoles:
    """has_any_of_roles: strict role membership, no permission fallback."""

    def test_true_when_member_holds_one_of_the_roles(self) -> None:
        """A single overlapping role is enough."""
        member = _member_with_roles(100, 200)

        assert has_any_of_roles(member=member, role_ids=[999, 200, 888]) is True

    def test_false_when_member_holds_none_of_the_roles(self) -> None:
        """No overlap means no permission."""
        member = _member_with_roles(100)

        assert has_any_of_roles(member=member, role_ids=[999]) is False

    def test_false_when_no_roles_are_configured(self) -> None:
        """An empty list denies everyone, even guild managers."""
        member = _member_with_roles(100)
        member.guild_permissions = MagicMock()
        member.guild_permissions.manage_guild = True

        assert has_any_of_roles(member=member, role_ids=[]) is False

    def test_false_when_member_has_no_roles(self) -> None:
        """A member with no roles never matches."""
        member = _member_with_roles()

        assert has_any_of_roles(member=member, role_ids=[100]) is False


class TestHasAnyRoleFallback:
    """has_any_role keeps the manage_guild fallback for an empty list."""

    def test_empty_list_falls_back_to_manage_guild(self) -> None:
        """With no roles configured, guild managers pass and others do not."""
        manager = _member_with_roles()
        manager.guild_permissions = MagicMock()
        manager.guild_permissions.manage_guild = True
        regular = _member_with_roles()
        regular.guild_permissions = MagicMock()
        regular.guild_permissions.manage_guild = False

        assert has_any_role(member=manager, role_ids=[]) is True
        assert has_any_role(member=regular, role_ids=[]) is False

    def test_non_empty_list_checks_membership_only(self) -> None:
        """With roles configured, manage_guild does not grant access."""
        manager = _member_with_roles(100)
        manager.guild_permissions = MagicMock()
        manager.guild_permissions.manage_guild = True

        assert has_any_role(member=manager, role_ids=[200]) is False
        assert has_any_role(member=manager, role_ids=[100]) is True
