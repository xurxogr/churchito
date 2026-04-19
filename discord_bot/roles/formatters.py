"""Message formatting utilities for roles cog."""

from __future__ import annotations

from typing import Any

import discord

from discord_bot.roles.models import ReactionPanel


def format_message(template: str | None, **kwargs: Any) -> str:
    r"""Replace placeholders in a message template.

    Placeholders use the format {placeholder_name}. Unknown placeholders
    are left unchanged, and None values are replaced with empty string.
    Literal \n sequences are converted to actual newlines.

    Args:
        template: Message template with {placeholders}
        **kwargs: Values for placeholders

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

    # Convert literal \n to actual newlines
    result = result.replace("\\n", "\n")

    return result


def format_emoji_display(emoji: str, emoji_id: int | None) -> str:
    """Format an emoji for display in text.

    Args:
        emoji: Emoji string (unicode or custom name)
        emoji_id: Custom emoji ID (None for unicode)

    Returns:
        str: Formatted emoji string
    """
    if emoji_id:
        # Custom emoji format: <:name:id> or <a:name:id> for animated
        return f"<:{emoji}:{emoji_id}>"
    return emoji


def _parse_color(color_value: Any, default: int = 0x5865F2) -> int:
    """Parse a color value to an integer.

    Args:
        color_value: Color as int, hex string (#RRGGBB), or None
        default: Default color if parsing fails

    Returns:
        int: Color as integer
    """
    if color_value is None:
        return default
    if isinstance(color_value, int):
        return color_value
    if isinstance(color_value, str):
        # Handle hex string like "#5865F2"
        color_str = color_value.strip().lstrip("#")
        try:
            return int(color_str, 16)
        except ValueError:
            return default
    return default


def build_panel_embed(
    panel: ReactionPanel,
    guild: discord.Guild,
    custom_config: dict[str, Any] | None = None,
) -> discord.Embed:
    """Build an embed for a reaction panel.

    Args:
        panel: The reaction panel
        guild: Discord guild
        custom_config: Optional custom embed config (overrides panel's config)

    Returns:
        discord.Embed: The panel embed
    """
    config = custom_config or panel.embed_config or {}

    title = config.get("title") or panel.name
    description = config.get("description")  # No default - empty means no description
    color = _parse_color(color_value=config.get("color"), default=0x5865F2)

    embed = discord.Embed(
        title=title,
        description=description if description else None,
        color=color,
    )

    # Add role options if mappings exist and field is not disabled
    show_roles_field = config.get("show_roles", True)
    if panel.role_mappings and show_roles_field:
        options_text = []
        for mapping in panel.role_mappings:
            emoji_display = format_emoji_display(
                emoji=mapping.get("emoji", ""),
                emoji_id=mapping.get("emoji_id"),
            )
            role_id = mapping.get("role_id")
            role = guild.get_role(int(role_id)) if role_id else None
            role_name = mapping.get("display_name") or (role.name if role else "Unknown Role")
            options_text.append(f"{emoji_display} - {role_name}")

        if options_text:
            # Default to "Roles", use zero-width space only if explicitly set to empty
            if "roles_field_name" in config:
                field_name = config["roles_field_name"] or "\u200b"
            else:
                field_name = "Roles"
            embed.add_field(
                name=field_name,
                value="\n".join(options_text),
                inline=False,
            )

    # Add footer - can be customized or disabled
    footer_text = config.get("footer")
    if footer_text is None:
        # Default footer based on panel type
        type_labels = {
            "toggle": "Toggle mode - click to add/remove",
            "exclusive": "Exclusive mode - only one role allowed",
            "verify": "Verify mode - one-time selection",
        }
        footer_text = type_labels.get(panel.panel_type, "")

    if footer_text:  # Only add footer if there's text
        embed.set_footer(text=footer_text)

    return embed


def build_panel_placeholder_data(
    panel: ReactionPanel,
    guild: discord.Guild,
    user: discord.Member | None = None,
) -> dict[str, Any]:
    """Build placeholder data dictionary from a ReactionPanel object.

    Args:
        panel: Panel to build data for
        guild: Discord guild
        user: Optional user who triggered the action

    Returns:
        dict[str, Any]: Dictionary with all placeholder values
    """
    channel = guild.get_channel(panel.channel_id)
    channel_mention = channel.mention if channel else f"<#{panel.channel_id}>"

    created_at_str = panel.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_unix = int(panel.created_at.timestamp())
    created_at_relative = f"<t:{created_at_unix}:R>"

    data: dict[str, Any] = {
        "panel_name": panel.name,
        "panel_type": panel.panel_type,
        "channel_mention": channel_mention,
        "guild_name": guild.name,
        "created_at": created_at_str,
        "created_at_relative": created_at_relative,
    }

    if user:
        data["user_name"] = user.display_name
        data["user_mention"] = user.mention

    # Format required roles
    if panel.required_roles:
        role_names = []
        for role_id in panel.required_roles:
            role = guild.get_role(role_id)
            role_names.append(role.name if role else f"Unknown({role_id})")
        data["required_roles"] = ", ".join(role_names)
    else:
        data["required_roles"] = "None"

    return data


def build_role_change_placeholder_data(
    panel: ReactionPanel,
    guild: discord.Guild,
    user: discord.Member,
    role: discord.Role,
) -> dict[str, Any]:
    """Build placeholder data for role change notifications.

    Args:
        panel: The reaction panel
        guild: Discord guild
        user: User who gained/lost the role
        role: The role that was added/removed

    Returns:
        dict[str, Any]: Dictionary with all placeholder values
    """
    data = build_panel_placeholder_data(panel=panel, guild=guild, user=user)
    data["role_name"] = role.name
    data["role_mention"] = role.mention
    return data


def format_mappings_display(
    mappings: list[dict[str, Any]],
    guild: discord.Guild,
) -> str:
    """Format role mappings for display.

    Args:
        mappings: List of emoji-role mappings
        guild: Discord guild for role resolution

    Returns:
        str: Formatted mappings string
    """
    if not mappings:
        return "No mappings configured"

    lines = []
    for mapping in mappings:
        emoji_display = format_emoji_display(
            emoji=mapping.get("emoji", ""),
            emoji_id=mapping.get("emoji_id"),
        )
        role = guild.get_role(mapping.get("role_id", 0))
        role_name = mapping.get("display_name") or (role.name if role else "Unknown Role")
        role_mention = role.mention if role else f"<@&{mapping.get('role_id', 0)}>"
        lines.append(f"{emoji_display} -> {role_mention} ({role_name})")

    return "\n".join(lines)
