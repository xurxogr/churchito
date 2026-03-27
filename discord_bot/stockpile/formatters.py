"""Message formatting utilities for stockpile cog."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

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


def format_roles_list(role_ids: list[int]) -> str:
    """Format a list of role IDs as Discord mentions.

    Args:
        role_ids (list[int]): List of role IDs

    Returns:
        str: Comma-separated role mentions or "Everyone" if empty
    """
    if not role_ids:
        return "Everyone"
    return ", ".join(f"<@&{role_id}>" for role_id in role_ids)


def format_stockpile_item(
    stockpile: Stockpile,
    template: str,
    hex_display_name: str,
) -> str:
    """Format a single stockpile for display.

    Args:
        stockpile (Stockpile): Stockpile to format
        template (str): Message template
        hex_display_name (str): Human-readable hex name

    Returns:
        str: Formatted stockpile string
    """
    created_at_str = stockpile.created_at.strftime("%Y-%m-%d %H:%M")
    roles_str = format_roles_list(stockpile.view_roles)

    return format_message(
        template,
        name=stockpile.name,
        code=stockpile.code,
        hex=hex_display_name,
        city=stockpile.city,
        roles=roles_str,
        creator=stockpile.created_by,
        created_at=created_at_str,
    )


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
