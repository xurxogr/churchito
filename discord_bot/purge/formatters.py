"""Formatting functions for the purge cog."""

from typing import Any

import discord

from discord_bot.purge.config import BUTTON_STYLES
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.models import PurgeRecord


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
    execution_logs: list[str] | None = None,
) -> str:
    """Generate moderation message content.

    Args:
        guild (discord.Guild): Guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Configuration.
        execution_logs (list[str] | None): Execution logs to append.

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
        dia=execution_date,
    )

    # Append execution logs if provided
    if execution_logs:
        logs_text = "\n".join(execution_logs)
        content = f"{content}\n\n**Logs:**\n{logs_text}"

    return content
