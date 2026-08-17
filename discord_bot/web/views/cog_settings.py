"""Builders for the cog settings partial (dashboard).

Everything here is side-effect free: given the Discord guild, the stored
configuration and the translations, produce the dictionaries the
``partials/cog_settings.html`` template consumes.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import discord

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption

logger = logging.getLogger(__name__)

_SNOWFLAKE_TYPES = (ConfigOptionType.CHANNEL, ConfigOptionType.ROLE)
_SNOWFLAKE_LIST_TYPES = (ConfigOptionType.CHANNEL_LIST, ConfigOptionType.ROLE_LIST)

_SAMPLE_JOINED_SERVER = "01/01/2024 12:00"
_SAMPLE_JOINED_SERVER_RELATIVE = "2 months ago"
_SAMPLE_JOINED_DISCORD = "01/06/2020 15:00"
_SAMPLE_JOINED_DISCORD_RELATIVE = "4 years ago"
_SAMPLE_USER_ID = "123456789"
_DEFAULT_AVATAR_URL = "https://cdn.discordapp.com/embed/avatars/0.png"


def format_relative_time(delta: timedelta) -> str:
    """Format a timedelta as relative text in English.

    Args:
        delta (timedelta): Time difference

    Returns:
        str: Text like "2 days ago", "3 months ago", etc.
    """
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "a few seconds ago"
    buckets = (
        (31536000, "year"),
        (2592000, "month"),
        (86400, "day"),
        (3600, "hour"),
        (60, "minute"),
    )
    for size, unit in buckets:
        if total_seconds >= size:
            count = total_seconds // size
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return "a few seconds ago"  # pragma: no cover - unreachable, keeps mypy happy


def list_sendable_channels(
    guild: discord.Guild, bot_member: discord.Member | None
) -> list[dict[str, Any]]:
    """List text channels the bot can post in, sorted by category and name.

    Args:
        guild (discord.Guild): Guild to inspect
        bot_member (discord.Member | None): Bot member for permission checks; None lists all

    Returns:
        list[dict[str, Any]]: Rows with string ``id`` (avoids JS precision loss), ``name``
            and ``category``
    """
    channels: list[dict[str, Any]] = []
    for channel in guild.text_channels:
        if bot_member and not channel.permissions_for(bot_member).send_messages:
            continue
        channels.append(
            {
                "id": str(channel.id),
                "name": channel.name,
                "category": channel.category.name if channel.category else None,
            }
        )
    channels.sort(key=lambda c: (c["category"] or "", c["name"]))
    return channels


def list_assignable_roles(guild: discord.Guild) -> list[dict[str, Any]]:
    """List roles below the bot's top role, excluding @everyone, sorted by name.

    Args:
        guild (discord.Guild): Guild to inspect

    Returns:
        list[dict[str, Any]]: Rows with string ``id``, ``name`` and ``color``
    """
    bot_top_role = guild.me.top_role
    roles = [
        {"id": str(role.id), "name": role.name, "color": str(role.color)}
        for role in guild.roles
        if role.name != "@everyone" and role < bot_top_role
    ]
    roles.sort(key=lambda r: r["name"].lower())
    return roles


def get_locked_options(bot: Any, cog_name: str) -> dict[str, dict[str, Any]]:
    """Ask the loaded cog which options are locked by deployment settings.

    Args:
        bot (Any): Bot instance (may be None)
        cog_name (str): Cog name, e.g. ``derived_roles``

    Returns:
        dict[str, dict[str, Any]]: Locked option key -> {locked, reason}; empty on any failure
    """
    if not bot:
        return {}
    cog = bot.get_cog(cog_name.title().replace("_", "") + "Cog")
    if not cog:
        return {}
    try:
        locked: dict[str, dict[str, Any]] = cog.get_locked_options()
    except Exception as e:
        logger.warning(f"Error getting locked options from {cog_name}: {e}")
        return {}
    return locked


def _channel_label(guild: discord.Guild, channel_id: Any) -> str:
    """Return ``#name`` for a channel ID, or ``ID: n`` if unknown.

    Args:
        guild (discord.Guild): Guild to resolve in
        channel_id (Any): Channel ID

    Returns:
        str: Display label
    """
    channel = guild.get_channel(channel_id)
    return f"#{channel.name}" if channel else f"ID: {channel_id}"


def _role_label(guild: discord.Guild, role_id: Any) -> str:
    """Return ``@name`` for a role ID, or ``ID: n`` if unknown.

    Args:
        guild (discord.Guild): Guild to resolve in
        role_id (Any): Role ID

    Returns:
        str: Display label
    """
    role = guild.get_role(role_id)
    return f"@{role.name}" if role else f"ID: {role_id}"


def resolve_display_value(option: ConfigOption, raw_value: Any, guild: discord.Guild | None) -> Any:
    """Turn stored channel/role IDs into human-readable names.

    Args:
        option (ConfigOption): Option being rendered
        raw_value (Any): Stored value (or default)
        guild (discord.Guild | None): Guild used to resolve names

    Returns:
        Any: Display value; the raw value for non-snowflake types or without a guild
    """
    if not raw_value or guild is None:
        return raw_value
    if option.option_type == ConfigOptionType.CHANNEL:
        return _channel_label(guild=guild, channel_id=raw_value)
    if option.option_type == ConfigOptionType.ROLE:
        return _role_label(guild=guild, role_id=raw_value)
    if option.option_type == ConfigOptionType.CHANNEL_LIST and isinstance(raw_value, list):
        return ", ".join(_channel_label(guild=guild, channel_id=cid) for cid in raw_value) or None
    if option.option_type == ConfigOptionType.ROLE_LIST and isinstance(raw_value, list):
        return ", ".join(_role_label(guild=guild, role_id=rid) for rid in raw_value) or None
    return raw_value


def to_template_value(option: ConfigOption, raw_value: Any) -> Any:
    """Stringify snowflake IDs so the template can compare them with dropdown options.

    Args:
        option (ConfigOption): Option being rendered
        raw_value (Any): Stored value (or default)

    Returns:
        Any: Value ready for the template
    """
    if raw_value is None:
        return None
    if option.option_type in _SNOWFLAKE_TYPES:
        return str(raw_value)
    if option.option_type in _SNOWFLAKE_LIST_TYPES and isinstance(raw_value, list):
        return [str(v) for v in raw_value]
    return raw_value


def translate_choices(
    option: ConfigOption,
    option_translations: dict[str, Any],
    choices_translations: dict[str, Any],
) -> list[tuple[str, Any]] | None:
    """Translate choice labels, preferring option-specific over shared choice groups.

    Args:
        option (ConfigOption): Option being rendered
        option_translations (dict[str, Any]): Translations for this option (may hold ``choices``)
        choices_translations (dict[str, Any]): Cog-wide choice groups (label -> translation)

    Returns:
        list[tuple[str, Any]] | None: Translated (label, value) pairs, or None without choices
    """
    if not option.choices:
        return None
    option_choices = option_translations.get("choices", {})
    translated: list[tuple[str, Any]] = []
    for label, value in option.choices:
        translated_label = option_choices.get(label)
        if translated_label is None:
            translated_label = next(
                (
                    group[label]
                    for group in choices_translations.values()
                    if isinstance(group, dict) and label in group
                ),
                label,
            )
        translated.append((translated_label, value))
    return translated


def translate_columns(
    option: ConfigOption, columns_translations: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Translate table column names without mutating the schema.

    Args:
        option (ConfigOption): Option being rendered
        columns_translations (dict[str, Any]): Column key -> translated name

    Returns:
        list[dict[str, Any]] | None: Copied columns with translated names, or None without columns
    """
    if not option.columns:
        return None
    return [
        {**col, "name": columns_translations[col["key"]]}
        if col.get("key") in columns_translations
        else dict(col)
        for col in option.columns
    ]


def build_option_data(
    option: ConfigOption,
    config_values: dict[str, Any],
    guild: discord.Guild | None,
    cog_translations: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the template row for one configuration option.

    Args:
        option (ConfigOption): Option to render
        config_values (dict[str, Any]): Stored configuration merged with defaults
        guild (discord.Guild | None): Guild used to resolve channel/role names
        cog_translations (dict[str, Any]): Translations for the cog in the active language

    Returns:
        dict[str, Any]: Row consumed by ``partials/cog_settings.html``
    """
    option_translations = cog_translations.get("options", {}).get(option.key, {})
    sections = cog_translations.get("sections", {})
    groups = cog_translations.get("groups", {})
    raw_value = config_values.get(option.key, option.default)

    return {
        "key": option.key,
        "name": option_translations.get("name", option.name),
        "description": option_translations.get("description", option.description),
        "type": option.option_type.value,
        "value": to_template_value(option=option, raw_value=raw_value),
        "display_value": resolve_display_value(option=option, raw_value=raw_value, guild=guild),
        "default": option.default,
        "required": option.required,
        "section": sections.get(option.section, option.section) if option.section else None,
        "group": groups.get(option.group, option.group) if option.group else None,
        "choices": translate_choices(
            option=option,
            option_translations=option_translations,
            choices_translations=cog_translations.get("choices", {}),
        ),
        "min_value": option.min_value,
        "max_value": option.max_value,
        "max_length": option.max_length,
        "placeholders": option.placeholders,
        "columns": translate_columns(
            option=option, columns_translations=cog_translations.get("columns", {})
        ),
    }


def _member_dates(member: discord.Member | None, now: datetime) -> dict[str, str]:
    """Format a member's join dates for the preview, or empty strings.

    Args:
        member (discord.Member | None): Member viewing the dashboard
        now (datetime): Current time (timezone-aware)

    Returns:
        dict[str, str]: Absolute and relative join dates (server and Discord)
    """
    dates = {
        "user_joined_server": "",
        "user_joined_server_relative": "",
        "user_joined_discord": "",
        "user_joined_discord_relative": "",
    }
    if member is None:
        return dates
    if member.joined_at:
        dates["user_joined_server"] = member.joined_at.strftime("%d/%m/%Y %H:%M")
        dates["user_joined_server_relative"] = format_relative_time(now - member.joined_at)
    if member.created_at:
        dates["user_joined_discord"] = member.created_at.strftime("%d/%m/%Y %H:%M")
        dates["user_joined_discord_relative"] = format_relative_time(now - member.created_at)
    return dates


def build_preview_data(
    guild_id: int,
    guild_name: str,
    member_count: int,
    user: dict[str, Any] | None,
    member: discord.Member | None,
    now: datetime,
) -> dict[str, str]:
    """Build sample values for the placeholder preview of message templates.

    Args:
        guild_id (int): Guild ID
        guild_name (str): Guild name
        member_count (int): Guild member count
        user (dict[str, Any] | None): Authenticated dashboard user
        member (discord.Member | None): That user's guild member, if resolvable
        now (datetime): Current time (timezone-aware)

    Returns:
        dict[str, str]: Placeholder name -> preview value
    """
    username = user.get("username", "User") if user else "User"
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{user.get('id')}/{user.get('avatar')}.png"
        if user and user.get("avatar")
        else _DEFAULT_AVATAR_URL
    )
    dates = _member_dates(member=member, now=now)
    return {
        "server_name": guild_name,
        "server_id": str(guild_id),
        "server_member_count": str(member_count),
        "user_name": username,
        "user_mention": f"@{username}",
        "user_id": str(user.get("id", _SAMPLE_USER_ID)) if user else _SAMPLE_USER_ID,
        "user_avatar_url": avatar_url,
        "user_joined_server": dates["user_joined_server"] or _SAMPLE_JOINED_SERVER,
        "user_joined_server_relative": dates["user_joined_server_relative"]
        or _SAMPLE_JOINED_SERVER_RELATIVE,
        "user_joined_discord": dates["user_joined_discord"] or _SAMPLE_JOINED_DISCORD,
        "user_joined_discord_relative": dates["user_joined_discord_relative"]
        or _SAMPLE_JOINED_DISCORD_RELATIVE,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "status": "📷 Waiting for screenshots",
        "verification_type": "Member",
        "username": username,
        # Player info placeholders (for verification API response preview)
        "name": "PlayerName",
        "regiment": "82DK",
        "level": "45",
        "faction": "colonial",
        "shard": "ABLE",
        "time": "268, 07:41",
        "war": "115",
        "war_time": "278, 08:34",
    }
