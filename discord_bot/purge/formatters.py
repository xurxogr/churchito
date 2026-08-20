"""Formatting functions for the purge cog."""

from collections.abc import Sequence
from typing import Any

import discord

from discord_bot.purge.config import BUTTON_STYLES
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.models import PurgeRecord

# Discord rejects message content longer than this
_MAX_CONTENT_LENGTH = 2000
_LOGS_HEADER = "\n\n**Logs:**\n"
_TRUNCATION_MARKER = "…"


def _fit_log_lines(*, lines: Sequence[str], available: int) -> str:
    """Join the newest log lines that fit in the available space.

    Older lines are dropped first; a truncation marker is prepended
    when any line had to be dropped.

    Args:
        lines (Sequence[str]): Log lines, oldest first.
        available (int): Maximum length of the joined text.

    Returns:
        str: Joined log text, empty if nothing fits.
    """
    if available <= 0:
        return ""

    kept: list[str] = []
    used = 0
    for line in reversed(lines):
        extra = len(line) if not kept else len(line) + 1
        if used + extra > available:
            break
        kept.append(line)
        used += extra

    if not kept:
        return ""
    if len(kept) < len(lines) and used + len(_TRUNCATION_MARKER) + 1 <= available:
        kept.append(_TRUNCATION_MARKER)
    return "\n".join(reversed(kept))


def format_message(template: str | None = None, **kwargs: str | None) -> str:
    """Replace placeholders in a message.

    Args:
        template (str | None): Message template.
        **kwargs: Placeholders to replace.

    Returns:
        str: Formatted message.
    """
    result = template or ""
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value or "")
    return result


def get_button_style(color: str) -> discord.ButtonStyle:
    """Get button style from color name.

    Args:
        color (str): Color name (blurple, grey, green, red).

    Returns:
        discord.ButtonStyle: Button style.
    """
    return BUTTON_STYLES.get(color, discord.ButtonStyle.success)


def format_authorized_by(guild: discord.Guild, user_ids: list[int]) -> str:
    """Format the list of users who authorized.

    Args:
        guild (discord.Guild): Guild to resolve names.
        user_ids (list[int]): List of user IDs.

    Returns:
        str: Formatted list of names.
    """
    if not user_ids:
        return "None"

    names: list[str] = []
    for user_id in user_ids:
        member = guild.get_member(user_id)
        if member:
            names.append(member.display_name)
        else:
            names.append(f"<@{user_id}>")

    return ", ".join(names)


def format_roles(guild: discord.Guild, role_ids: list[int]) -> str:
    """Format the list of roles.

    Args:
        guild (discord.Guild): Guild to resolve roles.
        role_ids (list[int]): List of role IDs.

    Returns:
        str: Formatted list of roles.
    """
    if not role_ids:
        return "None"

    roles: list[str] = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role.mention)
        else:
            roles.append(f"<@&{role_id}>")

    return ", ".join(roles)


def get_mod_message_content(
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    execution_logs: Sequence[str] | None = None,
) -> str:
    """Generate moderation message content.

    Args:
        guild (discord.Guild): Guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Configuration.
        execution_logs (Sequence[str] | None): Execution logs to append,
            trimmed to fit Discord's content length limit.

    Returns:
        str: Message content.
    """
    status_map = {
        PurgeStatus.PENDING: config.get(ConfigKey.MOD_STATUS_PENDING, ""),
        PurgeStatus.AUTHORIZED: config.get(ConfigKey.MOD_STATUS_AUTHORIZED, ""),
        PurgeStatus.EXPIRED: config.get(ConfigKey.MOD_STATUS_EXPIRED, ""),
        PurgeStatus.CANCEL_PENDING: config.get(ConfigKey.MOD_STATUS_CANCEL_PENDING, ""),
        PurgeStatus.CANCELLED: config.get(ConfigKey.MOD_STATUS_CANCELLED, ""),
        PurgeStatus.EXECUTED: config.get(ConfigKey.MOD_STATUS_EXECUTED, ""),
        PurgeStatus.FAILED: "❌ Failed",
    }

    status_text = status_map.get(PurgeStatus(record.status), "Unknown")
    required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
    authorized_by = format_authorized_by(guild=guild, user_ids=record.authorized_by)
    cancellations = format_authorized_by(guild=guild, user_ids=record.cancelled_by)

    # Get purge type name from config
    if record.purge_type == PurgeType.GLOBAL:
        purge_type = config.get(ConfigKey.GLOBAL_DISPLAY_NAME, "Global purge")
    else:
        # WAR_END
        purge_type = config.get(ConfigKey.WAR_DISPLAY_NAME, "War end purge")

    execution_date = "Not scheduled"
    if record.scheduled_for:
        execution_date = record.scheduled_for.strftime("%Y-%m-%d %H:%M UTC")

    content = format_message(
        template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
        purge_type=purge_type,
        status=status_text,
        required_reactions=str(required),
        authorized_by=authorized_by,
        cancellations=cancellations,
        date=execution_date,
        # Maintain compatibility with old placeholders
        dia=execution_date,
    )

    # The template is capped at Discord's content limit BEFORE the
    # placeholders (status, authorizer names, dates) are substituted, so the
    # rendered content can exceed it: Discord would 400 the send the purge
    # creation depends on, so the base content is clamped first
    if len(content) > _MAX_CONTENT_LENGTH:
        content = content[: _MAX_CONTENT_LENGTH - 1] + _TRUNCATION_MARKER

    # Append execution logs if provided, keeping the newest lines that fit
    if execution_logs:
        available = _MAX_CONTENT_LENGTH - len(content) - len(_LOGS_HEADER)
        logs_text = _fit_log_lines(lines=execution_logs, available=available)
        if logs_text:
            content = f"{content}{_LOGS_HEADER}{logs_text}"

    return content
