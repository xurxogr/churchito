"""Tests for the pure helpers in discord_bot/purge/phases.py."""

from unittest.mock import MagicMock

import discord

from discord_bot.purge.enums import ConfigKey
from discord_bot.purge.phases import (
    PhaseContext,
    _append_log,
    _replacement_roles,
    build_promotion_map,
)


def _context(config: dict, audit_level: int) -> PhaseContext:
    """Build a phase context with mocked live objects.

    Args:
        config (dict): Cog configuration.
        audit_level (int): Audit level.

    Returns:
        PhaseContext: Context with an empty execution log.
    """
    return PhaseContext(
        cog=MagicMock(),
        guild=MagicMock(),
        record=MagicMock(),
        config=config,
        audit_level=audit_level,
        execution_logs=[],
    )


class TestBuildPromotionMap:
    """Promotion list → from_role_id → to_role_id map."""

    def test_maps_int_and_legacy_string_ids(self) -> None:
        """String IDs from legacy data are coerced to int."""
        promotions = [
            {"from_role": 1, "to_role": 2},
            {"from_role": "3", "to_role": "4"},
        ]

        assert build_promotion_map(promotions) == {1: 2, 3: 4}

    def test_skips_incomplete_entries(self) -> None:
        """Entries missing either side are ignored."""
        promotions = [{"from_role": 1}, {"to_role": 2}, {"from_role": 0, "to_role": 5}, {}]

        assert build_promotion_map(promotions) == {}

    def test_last_duplicate_wins(self) -> None:
        """A repeated from_role keeps the last target."""
        promotions = [{"from_role": 1, "to_role": 2}, {"from_role": 1, "to_role": 3}]

        assert build_promotion_map(promotions) == {1: 3}


class TestAppendLog:
    """Audit-gated log lines."""

    def test_appends_formatted_line_when_level_reached(self) -> None:
        """The configured template is formatted and appended."""
        config = {ConfigKey.EXEC_MSG_PROMOTION_DEFAULT: "Default {role}"}
        ctx = _context(config=config, audit_level=2)

        _append_log(
            ctx=ctx,
            min_level=2,
            key=ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
            default="unused {role}",
            role="Member",
        )

        assert list(ctx.execution_logs) == ["Default Member"]

    def test_uses_default_template_when_not_configured(self) -> None:
        """Without a configured template the default is used."""
        ctx = _context(config={}, audit_level=1)

        _append_log(
            ctx=ctx,
            min_level=1,
            key=ConfigKey.EXEC_MSG_CLEANING_START,
            default="Start {role}",
            role="X",
        )

        assert list(ctx.execution_logs) == ["Start X"]

    def test_skips_below_audit_level(self) -> None:
        """Nothing is appended when the audit level is too low."""
        ctx = _context(config={}, audit_level=1)

        _append_log(ctx=ctx, min_level=2, key=ConfigKey.EXEC_MSG_CLEANING_ROLE, default="x")

        assert list(ctx.execution_logs) == []


def _role(role_id: int, name: str, assignable: bool = True) -> MagicMock:
    """Build a role mock.

    Args:
        role_id (int): Role ID.
        name (str): Role name.
        assignable (bool): Whether the bot can add/remove it. Defaults to True.

    Returns:
        MagicMock: Role mock.
    """
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    role.is_assignable.return_value = assignable
    return role


def _guild_with(
    member_roles: list[MagicMock], extra: list[MagicMock]
) -> tuple[MagicMock, MagicMock]:
    """Build a guild and a member holding ``member_roles`` (@everyone first).

    Args:
        member_roles (list[MagicMock]): Roles the member has (besides @everyone).
        extra (list[MagicMock]): Other guild roles resolvable by ID.

    Returns:
        tuple[MagicMock, MagicMock]: Guild and member mocks.
    """
    everyone = _role(0, "@everyone", assignable=False)
    guild = MagicMock(spec=discord.Guild)
    guild.name = "G"
    guild.default_role = everyone
    by_id = {r.id: r for r in [*member_roles, *extra]}
    guild.get_role.side_effect = lambda rid: by_id.get(rid)
    member = MagicMock(spec=discord.Member)
    member.name = "user"
    member.roles = [everyone, *member_roles]
    return guild, member


class TestReplacementRoles:
    """Target role list for one member.edit call; roles the bot cannot manage are untouched."""

    def test_remove_all_keeps_unassignable_roles(self) -> None:
        """Roles above the bot or managed ones survive a 'remove everything' cleaning."""
        below = _role(1, "Below")
        above = _role(2, "Above", assignable=False)
        booster = _role(3, "Booster", assignable=False)
        guild, member = _guild_with([below, above, booster], [])

        result = _replacement_roles(guild=guild, member=member, remove_ids=None, add_ids=[])

        assert result == [above, booster]

    def test_explicit_removal_skips_unassignable_roles(self) -> None:
        """A configured role the bot cannot remove is kept instead of failing the edit."""
        below = _role(1, "Below")
        above = _role(2, "Above", assignable=False)
        other = _role(3, "Other")
        guild, member = _guild_with([below, above, other], [])

        result = _replacement_roles(guild=guild, member=member, remove_ids={1, 2}, add_ids=[])

        assert result == [above, other]

    def test_unassignable_or_unknown_additions_are_skipped(self) -> None:
        """Roles the bot cannot assign (or that no longer exist) are not added."""
        kept = _role(1, "Kept")
        ok = _role(2, "Ok")
        above = _role(3, "Above", assignable=False)
        guild, member = _guild_with([kept], [ok, above])

        result = _replacement_roles(
            guild=guild, member=member, remove_ids=set(), add_ids=[2, 3, 404, 2]
        )

        assert result == [kept, ok]
