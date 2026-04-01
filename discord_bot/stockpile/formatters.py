"""Message formatting utilities for stockpile cog."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from discord_bot.stockpile.models import Stockpile


def format_message(template: str | None, **kwargs: Any) -> str:
    """Replace placeholders in a message template.

    Placeholders use the format {placeholder_name}. Unknown placeholders
    are left unchanged, and None values are replaced with empty string.

    Args:
        template (str | None): Message template with {placeholders}
        **kwargs (Any): Values for placeholders

    Returns:
        str: Formatted message
    """
    if not template:
        return ""

    result = template
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        if value is None:
            value = ""
        result = result.replace(placeholder, str(value))

    return result


def format_roles_list(
    role_ids: list[int],
    guild: discord.Guild | None = None,
) -> str:
    """Format a list of role IDs as names (if guild provided) or mentions.

    Args:
        role_ids (list[int]): List of role IDs
        guild (discord.Guild | None): Optional guild to resolve role names

    Returns:
        str: Comma-separated role names/mentions or "Everyone" if empty
    """
    if not role_ids:
        return "Everyone"
    if guild:
        names = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            names.append(role.name if role else f"Unknown({role_id})")
        return ", ".join(names)
    return ", ".join(f"<@&{role_id}>" for role_id in role_ids)


def build_stockpile_embed_context(
    *,
    name: str,
    code: str,
    hex_display: str,
    city: str,
    created_at: Any,  # datetime
    role_ids: list[int] | None = None,
    roles: list[discord.Role] | None = None,
    creator_id: int | None = None,
    creator: discord.Member | None = None,
    guild: discord.Guild | None = None,
    deleted_by: discord.Member | None = None,
) -> dict[str, Any]:
    """Build placeholder data dictionary for stockpile embeds.

    This is the single source of truth for stockpile placeholder data.
    Used by add notifications, delete notifications, and show command.

    Args:
        name: Stockpile name
        code: Stockpile code
        hex_display: Human-readable hex name
        city: City name
        created_at: Creation datetime
        role_ids: List of role IDs (used if roles not provided)
        roles: List of discord.Role objects (preferred over role_ids)
        creator_id: Creator user ID (used if creator not provided)
        creator: Creator as discord.Member (preferred over creator_id)
        guild: Guild to resolve role/member names
        deleted_by: Member who deleted (only for delete notifications)

    Returns:
        dict[str, Any]: Dictionary with all placeholder values
    """
    # Format created_at
    created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
    created_at_unix = int(created_at.timestamp())
    created_at_relative = f"<t:{created_at_unix}:R>"

    # Build roles strings
    if roles is not None:
        roles_str = ", ".join(r.name for r in roles) if roles else "Everyone"
        roles_mention_str = ", ".join(r.mention for r in roles) if roles else "Everyone"
    elif role_ids is not None:
        roles_str = format_roles_list(role_ids, guild)
        roles_mention_str = format_roles_list(role_ids)
    else:
        roles_str = "Everyone"
        roles_mention_str = "Everyone"

    # Build creator strings
    if creator is not None:
        creator_str = creator.display_name
        creator_mention_str = creator.mention
    elif creator_id is not None:
        if guild:
            member = guild.get_member(creator_id)
            creator_str = member.display_name if member else f"Unknown({creator_id})"
        else:
            creator_str = str(creator_id)
        creator_mention_str = f"<@{creator_id}>"
    else:
        creator_str = "Unknown"
        creator_mention_str = "Unknown"

    data = {
        "name": name,
        "code": code,
        "hex": hex_display,
        "city": city,
        "roles": roles_str,
        "roles_mention": roles_mention_str,
        "creator": creator_str,
        "creator_mention": creator_mention_str,
        "created_at": created_at_str,
        "created_at_relative": created_at_relative,
    }

    # Add deleted_by fields if provided
    if deleted_by is not None:
        data["deleted_by"] = deleted_by.display_name
        data["deleted_by_mention"] = deleted_by.mention

    return data


def build_stockpile_placeholder_data(
    stockpile: Stockpile,
    hex_display_name: str,
    guild: discord.Guild | None = None,
) -> dict[str, Any]:
    """Build placeholder data dictionary from a Stockpile object.

    Convenience wrapper around build_stockpile_embed_context for Stockpile objects.

    Args:
        stockpile (Stockpile): Stockpile to build data for
        hex_display_name (str): Human-readable hex name
        guild (discord.Guild | None): Optional guild to resolve role names and creator

    Returns:
        dict[str, Any]: Dictionary with all placeholder values
    """
    return build_stockpile_embed_context(
        name=stockpile.name,
        code=stockpile.code,
        hex_display=hex_display_name,
        city=stockpile.city,
        created_at=stockpile.created_at,
        role_ids=stockpile.view_roles,
        creator_id=stockpile.created_by,
        guild=guild,
    )


def format_stockpile_item(
    stockpile: Stockpile,
    template: str,
    hex_display_name: str,
    guild: discord.Guild | None = None,
) -> str:
    """Format a single stockpile for display.

    Args:
        stockpile (Stockpile): Stockpile to format
        template (str): Message template
        hex_display_name (str): Human-readable hex name
        guild (discord.Guild | None): Optional guild to resolve role names and creator

    Returns:
        str: Formatted stockpile string
    """
    data = build_stockpile_placeholder_data(stockpile, hex_display_name, guild)
    return format_message(template, **data)


def group_stockpiles_by_location(
    stockpiles: list[Stockpile],
) -> dict[tuple[str, str], list[Stockpile]]:
    """Group stockpiles by (hex_key, city).

    Args:
        stockpiles (list[Stockpile]): List of stockpiles to group

    Returns:
        dict[tuple[str, str], list[Stockpile]]: Mapping of (hex_key, city) to list of stockpiles
    """
    grouped: dict[tuple[str, str], list[Stockpile]] = {}
    for stockpile in stockpiles:
        key = (stockpile.hex_key, stockpile.city)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(stockpile)
    return grouped


def validate_code(code: str) -> bool:
    """Validate that a code is exactly 6 digits.

    Args:
        code (str): Code to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return bool(re.match(r"^\d{6}$", code))


def format_pinned_message(
    stockpiles: list[Stockpile],
    header_template: str,
    item_template: str,
    guild: discord.Guild,
    hex_display_name_func: Any,
) -> discord.Embed | None:
    """Format the complete pinned message as an embed with all stockpiles grouped by location.

    Args:
        stockpiles (list[Stockpile]): List of all stockpiles
        header_template (str): Template for location headers
        item_template (str): Template for each stockpile item
        guild (discord.Guild): Guild to resolve role names
        hex_display_name_func: Function to convert hex_key to display name

    Returns:
        discord.Embed | None: Formatted embed or None if no stockpiles
    """
    if not stockpiles:
        return None

    grouped = group_stockpiles_by_location(stockpiles)
    lines: list[str] = []

    for (hex_key, city), location_stockpiles in grouped.items():
        hex_display = hex_display_name_func(hex_key)

        # Add header
        header = format_message(
            header_template,
            hex=hex_display,
            city=city,
            count=len(location_stockpiles),
        )
        lines.append(header)

        # Add items
        for stockpile in location_stockpiles:
            created_at_str = stockpile.created_at.strftime("%Y-%m-%d %H:%M")
            # Discord relative timestamp format: <t:UNIX:R> shows "X ago"
            created_at_unix = int(stockpile.created_at.timestamp())
            created_at_relative = f"<t:{created_at_unix}:R>"
            # Role names (no mentions)
            roles_str = format_roles_list(stockpile.view_roles, guild)
            # Role mentions
            roles_mention_str = format_roles_list(stockpile.view_roles)

            # Resolve creator to display name (no @mention)
            member = guild.get_member(stockpile.created_by)
            creator_str = member.display_name if member else f"Unknown({stockpile.created_by})"
            # Creator mention
            creator_mention_str = f"<@{stockpile.created_by}>"

            item = format_message(
                item_template,
                name=stockpile.name,
                code=stockpile.code,
                hex=hex_display,
                city=city,
                roles=roles_str,
                roles_mention=roles_mention_str,
                creator=creator_str,
                creator_mention=creator_mention_str,
                created_at=created_at_str,
                created_at_relative=created_at_relative,
            )
            lines.append(item)

    description = "\n".join(lines)

    # Discord embed description limit is 4096 characters
    if len(description) > 4096:
        description = description[:4093] + "..."

    return discord.Embed(description=description)
