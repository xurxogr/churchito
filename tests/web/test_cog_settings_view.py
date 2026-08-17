"""Tests for the cog settings view builders."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import discord

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.web.views.cog_settings import (
    build_option_data,
    build_preview_data,
    format_relative_time,
    get_locked_options,
    list_assignable_roles,
    list_sendable_channels,
    resolve_display_value,
    to_template_value,
    translate_choices,
    translate_columns,
)


def _channel(channel_id: int, name: str, category: str | None, can_send: bool) -> MagicMock:
    """Build a text channel mock.

    Args:
        channel_id (int): Channel ID.
        name (str): Channel name.
        category (str | None): Category name.
        can_send (bool): Whether the bot may send messages.

    Returns:
        MagicMock: Channel mock.
    """
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.category = MagicMock(name=category) if category else None
    if channel.category:
        channel.category.name = category
    channel.permissions_for.return_value = MagicMock(send_messages=can_send)
    return channel


def _role(role_id: int, name: str, position: int) -> MagicMock:
    """Build a role mock comparable by position.

    Args:
        role_id (int): Role ID.
        name (str): Role name.
        position (int): Role position (higher is above).

    Returns:
        MagicMock: Role mock.
    """
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    role.color = "#ff0000"
    role.position = position
    role.__lt__ = lambda self, other: self.position < other.position
    return role


def _guild(channels: list[MagicMock], roles: list[MagicMock]) -> MagicMock:
    """Build a guild mock exposing channels/roles lookups.

    Args:
        channels (list[MagicMock]): Text channels.
        roles (list[MagicMock]): Roles including the bot's top role last.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = channels
    guild.roles = roles
    guild.me = MagicMock()
    guild.me.top_role = roles[-1] if roles else None
    guild.get_channel.side_effect = lambda cid: next((c for c in channels if c.id == cid), None)
    guild.get_role.side_effect = lambda rid: next((r for r in roles if r.id == rid), None)
    return guild


class TestGuildLists:
    """Channel and role dropdown sources."""

    def test_sendable_channels_filtered_and_sorted(self) -> None:
        """Only channels the bot can post in are listed, sorted by category then name."""
        channels = [
            _channel(3, "zeta", "B", True),
            _channel(1, "alpha", "B", True),
            _channel(2, "locked", "A", False),
            _channel(4, "uncategorized", None, True),
        ]
        bot_member = MagicMock(spec=discord.Member)

        result = list_sendable_channels(guild=_guild(channels, []), bot_member=bot_member)

        assert [c["id"] for c in result] == ["4", "1", "3"]
        assert result[1] == {"id": "1", "name": "alpha", "category": "B"}

    def test_sendable_channels_without_bot_member_lists_all(self) -> None:
        """Without a bot member to check permissions, every channel is listed."""
        channels = [_channel(1, "a", None, False)]

        result = list_sendable_channels(guild=_guild(channels, []), bot_member=None)

        assert [c["id"] for c in result] == ["1"]

    def test_assignable_roles_excludes_everyone_and_higher_roles(self) -> None:
        """@everyone and roles at or above the bot's top role are excluded; sorted by name."""
        roles = [
            _role(1, "@everyone", 0),
            _role(2, "zulu", 1),
            _role(3, "Alpha", 2),
            _role(4, "Above", 5),
            _role(5, "BotTop", 4),
        ]

        result = list_assignable_roles(guild=_guild([], roles))

        assert [r["id"] for r in result] == ["3", "2"]
        assert result[0] == {"id": "3", "name": "Alpha", "color": "#ff0000"}


class TestLockedOptions:
    """Locked options come from the loaded cog, tolerating failures."""

    def test_returns_cog_locked_options(self) -> None:
        """The cog class name is derived from the cog name."""
        bot = MagicMock()
        cog = MagicMock()
        cog.get_locked_options.return_value = {"key": {"locked": True}}
        bot.get_cog.return_value = cog

        assert get_locked_options(bot=bot, cog_name="derived_roles") == {"key": {"locked": True}}
        bot.get_cog.assert_called_once_with("DerivedRolesCog")

    def test_missing_bot_cog_or_error_yields_empty(self) -> None:
        """No bot, no cog, or a raising cog all yield no locked options."""
        assert get_locked_options(bot=None, cog_name="x") == {}

        bot = MagicMock()
        bot.get_cog.return_value = None
        assert get_locked_options(bot=bot, cog_name="x") == {}

        cog = MagicMock()
        cog.get_locked_options.side_effect = RuntimeError("boom")
        bot.get_cog.return_value = cog
        assert get_locked_options(bot=bot, cog_name="x") == {}


class TestValueRendering:
    """Display and template values per option type."""

    def test_display_value_resolves_names_and_unknown_ids(self) -> None:
        """Channels/roles resolve to names; unknown IDs fall back to 'ID: n'."""
        guild = _guild([_channel(10, "general", None, True)], [_role(20, "Admin", 1)])
        channel_opt = ConfigOption(
            key="c", name="c", option_type=ConfigOptionType.CHANNEL, default=None
        )
        role_list_opt = ConfigOption(
            key="r", name="r", option_type=ConfigOptionType.ROLE_LIST, default=[]
        )

        assert resolve_display_value(option=channel_opt, raw_value=10, guild=guild) == "#general"
        assert resolve_display_value(option=channel_opt, raw_value=99, guild=guild) == "ID: 99"
        assert (
            resolve_display_value(option=role_list_opt, raw_value=[20, 21], guild=guild)
            == "@Admin, ID: 21"
        )
        assert resolve_display_value(option=role_list_opt, raw_value=[], guild=guild) == []
        assert resolve_display_value(option=channel_opt, raw_value=10, guild=None) == 10

    def test_template_value_stringifies_snowflakes(self) -> None:
        """Snowflake IDs become strings (and lists of strings) for the template."""
        channel_opt = ConfigOption(
            key="c", name="c", option_type=ConfigOptionType.CHANNEL, default=None
        )
        role_list_opt = ConfigOption(
            key="r", name="r", option_type=ConfigOptionType.ROLE_LIST, default=[]
        )
        int_opt = ConfigOption(key="i", name="i", option_type=ConfigOptionType.INTEGER, default=0)

        assert to_template_value(option=channel_opt, raw_value=10) == "10"
        assert to_template_value(option=channel_opt, raw_value=None) is None
        assert to_template_value(option=role_list_opt, raw_value=[1, 2]) == ["1", "2"]
        assert to_template_value(option=int_opt, raw_value=5) == 5


class TestTranslations:
    """Choice and column translation."""

    def test_translate_choices_prefers_option_specific_then_groups(self) -> None:
        """Option-level choice translations win over shared choice groups."""
        opt = ConfigOption(
            key="k",
            name="k",
            option_type=ConfigOptionType.TEXT_CHOICE,
            default="a",
            choices=[("A", "a"), ("B", "b"), ("C", "c")],
        )

        result = translate_choices(
            option=opt,
            option_translations={"choices": {"A": "Alpha"}},
            choices_translations={"group": {"B": "Beta"}, "not_a_dict": "x"},
        )

        assert result == [("Alpha", "a"), ("Beta", "b"), ("C", "c")]

    def test_translate_choices_none_without_choices(self) -> None:
        """Options without choices yield None."""
        opt = ConfigOption(key="k", name="k", option_type=ConfigOptionType.STRING, default="")

        result = translate_choices(option=opt, option_translations={}, choices_translations={})

        assert result is None

    def test_translate_columns_copies_and_renames(self) -> None:
        """Column dicts are copied with translated names; originals untouched."""
        columns: list[dict[str, Any]] = [{"key": "a", "name": "A"}, {"key": "b", "name": "B"}]
        opt = ConfigOption(
            key="t", name="t", option_type=ConfigOptionType.TABLE, default=[], columns=columns
        )

        result = translate_columns(option=opt, columns_translations={"a": "Alpha"})

        assert result == [{"key": "a", "name": "Alpha"}, {"key": "b", "name": "B"}]
        assert columns[0]["name"] == "A"
        no_columns = ConfigOption(
            key="s", name="s", option_type=ConfigOptionType.STRING, default=""
        )
        assert translate_columns(option=no_columns, columns_translations={}) is None


class TestBuildOptionData:
    """Assembling one option row for the template."""

    def test_option_row_uses_translations_and_values(self) -> None:
        """Name/description/section/group are translated and values resolved."""
        guild = _guild([_channel(10, "general", None, True)], [])
        opt = ConfigOption(
            key="c",
            name="Channel",
            description="Where",
            option_type=ConfigOptionType.CHANNEL,
            default=None,
            section="main",
            group="g",
        )
        translations = {
            "options": {"c": {"name": "Canal", "description": "Dónde"}},
            "sections": {"main": "Principal"},
            "groups": {"g": "Grupo"},
        }

        row = build_option_data(
            option=opt, config_values={"c": 10}, guild=guild, cog_translations=translations
        )

        assert row["name"] == "Canal"
        assert row["description"] == "Dónde"
        assert row["section"] == "Principal"
        assert row["group"] == "Grupo"
        assert row["value"] == "10"
        assert row["display_value"] == "#general"
        assert row["type"] == "channel"


class TestFormatRelativeTime:
    """Tests for format_relative_time."""

    def test_seconds(self) -> None:
        """Test format for seconds."""
        result = format_relative_time(timedelta(seconds=30))
        assert result == "a few seconds ago"

    def test_one_minute(self) -> None:
        """Test format for 1 minute."""
        result = format_relative_time(timedelta(minutes=1))
        assert result == "1 minute ago"

    def test_multiple_minutes(self) -> None:
        """Test format for multiple minutes."""
        result = format_relative_time(timedelta(minutes=45))
        assert result == "45 minutes ago"

    def test_one_hour(self) -> None:
        """Test format for 1 hour."""
        result = format_relative_time(timedelta(hours=1))
        assert result == "1 hour ago"

    def test_multiple_hours(self) -> None:
        """Test format for multiple hours."""
        result = format_relative_time(timedelta(hours=12))
        assert result == "12 hours ago"

    def test_one_day(self) -> None:
        """Test format for 1 day."""
        result = format_relative_time(timedelta(days=1))
        assert result == "1 day ago"

    def test_multiple_days(self) -> None:
        """Test format for multiple days."""
        result = format_relative_time(timedelta(days=15))
        assert result == "15 days ago"

    def test_one_month(self) -> None:
        """Test format for 1 month (~30 days)."""
        result = format_relative_time(timedelta(days=30))
        assert result == "1 month ago"

    def test_multiple_months(self) -> None:
        """Test format for multiple months."""
        result = format_relative_time(timedelta(days=180))
        assert result == "6 months ago"

    def test_one_year(self) -> None:
        """Test format for 1 year (~365 days)."""
        result = format_relative_time(timedelta(days=365))
        assert result == "1 year ago"

    def test_multiple_years(self) -> None:
        """Test format for multiple years."""
        result = format_relative_time(timedelta(days=730))
        assert result == "2 years ago"


class TestPreviewData:
    """Placeholder preview values."""

    def test_preview_with_member_and_user(self) -> None:
        """Real member dates and user identity feed the preview."""
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        member = MagicMock(spec=discord.Member)
        member.joined_at = now - timedelta(days=3)
        member.created_at = now - timedelta(days=800)
        user = {"id": "42", "username": "neo", "avatar": "abc"}

        preview = build_preview_data(
            guild_id=1, guild_name="G", member_count=7, user=user, member=member, now=now
        )

        assert preview["server_name"] == "G"
        assert preview["server_member_count"] == "7"
        assert preview["user_name"] == "neo"
        assert preview["user_mention"] == "@neo"
        assert preview["user_avatar_url"] == "https://cdn.discordapp.com/avatars/42/abc.png"
        assert preview["user_joined_server_relative"] == "3 days ago"
        assert preview["user_joined_discord_relative"] == "2 years ago"
        assert preview["created_at"] == "2026-01-10 12:00"

    def test_preview_without_user_uses_placeholders(self) -> None:
        """Anonymous preview falls back to sample values."""
        now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)

        preview = build_preview_data(
            guild_id=1, guild_name="G", member_count=0, user=None, member=None, now=now
        )

        assert preview["user_name"] == "User"
        assert preview["user_id"] == "123456789"
        assert preview["user_avatar_url"] == "https://cdn.discordapp.com/embed/avatars/0.png"
        assert preview["user_joined_server"] == "01/01/2024 12:00"
