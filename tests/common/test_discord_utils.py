"""Tests for role helpers in discord_bot.common.utils.discord."""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

import discord

from discord_bot.common.utils import has_any_of_roles, has_any_role, utc_timestamp


@contextmanager
def _forced_timezone(name: str) -> Iterator[None]:
    """Temporarily switch the process timezone, restoring it afterwards.

    Args:
        name (str): TZ database name, e.g. "America/New_York".
    """
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


class TestUtcTimestamp:
    """Tests for utc_timestamp."""

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        """A naive datetime (as SQLite returns them) must be read as UTC, not local time."""
        aware = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)
        naive = aware.replace(tzinfo=None)

        with _forced_timezone("America/New_York"):
            assert utc_timestamp(naive) == int(aware.timestamp())

    def test_aware_datetime_is_unchanged(self) -> None:
        """A timezone-aware datetime keeps its own instant regardless of host timezone."""
        aware = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)

        with _forced_timezone("America/New_York"):
            assert utc_timestamp(aware) == int(aware.timestamp())


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
