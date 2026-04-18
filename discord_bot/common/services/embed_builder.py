"""Service for building configurable embeds with placeholders."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import discord
from discord import Guild, Member

from discord_bot.common.enums.embed_section_type import EmbedSectionType
from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection

# Dot emoji mappings (colored circle emojis)
DOT_EMOJIS: dict[str, str] = {
    "dot_red": "🔴",
    "dot_green": "🟢",
    "dot_yellow": "🟡",
    "dot_blue": "🔵",
    "dot_white": "⚪",
    "dot_black": "⚫",
    "dot_orange": "🟠",
    "dot_purple": "🟣",
    "dot_brown": "🟤",
}

# ANSI color codes for Discord code blocks
ANSI_COLORS: dict[str, str] = {
    "gray": "\u001b[2;30m",
    "red": "\u001b[2;31m",
    "green": "\u001b[2;32m",
    "yellow": "\u001b[2;33m",
    "blue": "\u001b[2;34m",
    "pink": "\u001b[2;35m",
    "cyan": "\u001b[2;36m",
    "white": "\u001b[2;37m",
}
ANSI_RESET = "\u001b[0m"


@dataclass
class PlaceholderContext:
    """Context with data for resolving placeholders.

    Global placeholders (server_*, user_*) are resolved automatically
    if guild and/or member are provided. Additional placeholders can
    be passed in extra_data.
    """

    guild: Guild | None = None
    member: Member | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)

    def resolve(self, key: str) -> str | None:
        """Resolve a placeholder by its key.

        Args:
            key: Placeholder name without braces.

        Returns:
            Resolved value or None if not found.
        """
        # First look in extra_data (allows override of globals)
        if key in self.extra_data:
            value = self.extra_data[key]
            return str(value) if value is not None else None

        # Dot emoji placeholders
        if key in DOT_EMOJIS:
            return DOT_EMOJIS[key]

        # Server placeholders
        if self.guild:
            if key == "server_name":
                return self.guild.name
            if key == "server_id":
                return str(self.guild.id)
            if key == "server_member_count":
                return str(self.guild.member_count)

        # User placeholders
        if self.member:
            if key == "user_name":
                return self.member.display_name
            if key == "user_mention":
                return self.member.mention
            if key == "user_id":
                return str(self.member.id)
            if key == "user_discriminator":
                return self.member.discriminator
            if key == "user_avatar_url":
                return str(self.member.display_avatar.url)
            if key == "user_joined_server":
                if self.member.joined_at:
                    return self.member.joined_at.strftime("%Y-%m-%d %H:%M")
                return "N/A"
            if key == "user_joined_server_relative":
                if self.member.joined_at:
                    return f"<t:{int(self.member.joined_at.timestamp())}:R>"
                return "N/A"
            if key == "user_joined_discord":
                return self.member.created_at.strftime("%Y-%m-%d %H:%M")
            if key == "user_joined_discord_relative":
                return f"<t:{int(self.member.created_at.timestamp())}:R>"

        return None


# List of available global placeholders
GLOBAL_PLACEHOLDERS: list[dict[str, str]] = [
    # Server
    {"key": "server_name", "description": "Server name"},
    {"key": "server_id", "description": "Server ID"},
    {"key": "server_member_count", "description": "Member count"},
    # User
    {"key": "user_name", "description": "User's name"},
    {"key": "user_display_name", "description": "User's display name (plain text)"},
    {"key": "user_mention", "description": "User mention"},
    {"key": "user_id", "description": "User ID"},
    {"key": "user_avatar_url", "description": "Avatar URL"},
    {"key": "user_joined_server", "description": "Server join date"},
    {"key": "user_joined_server_relative", "description": "Time since joined (relative)"},
    {"key": "user_joined_discord", "description": "Account creation date"},
    {"key": "user_joined_discord_relative", "description": "Account age (relative)"},
    # Dot emojis (colored circles)
    {"key": "dot_red", "description": "🔴 Red circle"},
    {"key": "dot_green", "description": "🟢 Green circle"},
    {"key": "dot_yellow", "description": "🟡 Yellow circle"},
    {"key": "dot_blue", "description": "🔵 Blue circle"},
    {"key": "dot_white", "description": "⚪ White circle"},
    {"key": "dot_black", "description": "⚫ Black circle"},
    {"key": "dot_orange", "description": "🟠 Orange circle"},
    {"key": "dot_purple", "description": "🟣 Purple circle"},
    {"key": "dot_brown", "description": "🟤 Brown circle"},
]

# Color tags available for ANSI formatting
COLOR_TAGS: list[dict[str, str]] = [
    {"tag": "{red}...{/red}", "description": "Red text (ANSI)"},
    {"tag": "{green}...{/green}", "description": "Green text (ANSI)"},
    {"tag": "{yellow}...{/yellow}", "description": "Yellow text (ANSI)"},
    {"tag": "{blue}...{/blue}", "description": "Blue text (ANSI)"},
    {"tag": "{pink}...{/pink}", "description": "Pink text (ANSI)"},
    {"tag": "{cyan}...{/cyan}", "description": "Cyan text (ANSI)"},
    {"tag": "{white}...{/white}", "description": "White text (ANSI)"},
    {"tag": "{gray}...{/gray}", "description": "Gray text (ANSI)"},
]


def _has_color_tags(text: str) -> bool:
    """Check if text contains any ANSI color tags.

    Args:
        text: Text to check.

    Returns:
        True if text contains color tags like {red}, {/red}, etc.
    """
    # Match opening tags like {red}, {green}, etc.
    pattern = r"\{(" + "|".join(ANSI_COLORS.keys()) + r")\}"
    return bool(re.search(pattern, text))


def _apply_ansi_colors(text: str) -> str:
    """Convert color tags to ANSI codes and wrap in code block.

    Args:
        text: Text with color tags like {red}text{/red}.

    Returns:
        Text wrapped in ANSI code block with color codes applied.
    """
    result = text

    # Replace opening color tags with ANSI codes
    for color, code in ANSI_COLORS.items():
        result = result.replace(f"{{{color}}}", code)
        result = result.replace(f"{{/{color}}}", ANSI_RESET)

    # Wrap in ANSI code block
    return f"```ansi\n{result}\n```"


def format_placeholders(template: str, context: PlaceholderContext) -> str:
    """Replace placeholders in a template.

    Args:
        template: Text with placeholders in {name} format.
        context: Context with data for resolution.

    Returns:
        Text with placeholders replaced.
    """
    result = template
    # Find all placeholders {xxx}
    placeholders = re.findall(r"\{(\w+)\}", template)

    for key in placeholders:
        value = context.resolve(key)
        if value is not None:
            result = result.replace(f"{{{key}}}", value)

    # Convert literal \n to actual newlines
    result = result.replace("\\n", "\n")

    return result


def format_with_colors(text: str, context: PlaceholderContext) -> str:
    """Format text with placeholders and apply ANSI colors if present.

    Args:
        text: Text with placeholders and optional color tags.
        context: Context for placeholder resolution.

    Returns:
        Formatted text. If color tags were present, wrapped in ANSI code block.
    """
    # First resolve placeholders
    result = format_placeholders(text, context)

    # Then check for and apply ANSI colors
    if _has_color_tags(result):
        result = _apply_ansi_colors(result)

    return result


def create_progress_bar(
    value: int | float,
    max_value: int | float,
    length: int = 10,
    filled_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Create a progress bar with Unicode characters.

    Args:
        value: Current value.
        max_value: Maximum value.
        length: Bar length in characters.
        filled_char: Character for filled part.
        empty_char: Character for empty part.

    Returns:
        Progress bar as string.
    """
    if max_value <= 0:
        return empty_char * length

    percentage = min(value / max_value, 1.0)
    filled = int(percentage * length)
    return filled_char * filled + empty_char * (length - filled)


def _parse_hex_color(hex_color: str | None) -> discord.Color | None:
    """Parse a hexadecimal color to discord.Color."""
    if not hex_color:
        return None
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return discord.Color(int(hex_color, 16))
    except ValueError:
        return None


def _render_section(section: EmbedSection, context: PlaceholderContext) -> dict[str, Any]:
    """Render a section to embed data.

    Returns:
        Dict with 'fields' (fields to add). All sections are now fields.
    """
    # Zero-width space for empty field names/values (Discord requires non-empty)
    EMPTY = "\u200b"
    result: dict[str, Any] = {"fields": []}

    match section.type:
        case EmbedSectionType.TEXT:
            # Full-width field with title + content
            # Title uses regular placeholders (no ANSI - would look bad in field name)
            title = format_placeholders(section.title, context) if section.title else EMPTY
            # Content supports ANSI colors
            content = format_with_colors(section.content, context) if section.content else EMPTY
            result["fields"].append(
                {
                    "name": title,
                    "value": content,
                    "inline": False,
                }
            )

        case EmbedSectionType.FIELDS:
            # Inline fields (up to 3 per row)
            fields = section.get_fields()
            for field_item in fields:
                result["fields"].append(
                    {
                        # Field names use regular placeholders (no ANSI)
                        "name": format_placeholders(field_item.name, context),
                        # Field values support ANSI colors
                        "value": format_with_colors(field_item.value, context),
                        "inline": section.inline,
                    }
                )

    return result


class EmbedFieldLimitError(Exception):
    """Error when the 25 field limit is exceeded in an embed."""

    def __init__(self, field_count: int) -> None:
        """Initialize the error.

        Args:
            field_count: Number of fields attempted to add.
        """
        self.field_count = field_count
        super().__init__(f"Embed exceeds the 25 field limit ({field_count} fields)")


def build_embed(
    config: EmbedConfig,
    context: PlaceholderContext,
    *,
    title: str | None = None,
    default_color: discord.Color | None = None,
    validate_fields: bool = True,
) -> discord.Embed:
    """Build an embed from a section configuration.

    Args:
        config: Embed configuration with sections.
        context: Context with data for resolving placeholders.
        title: Optional title (overrides config.title if provided).
        default_color: Default color if no color in config.
        validate_fields: If True, raises error if 25 fields exceeded.

    Returns:
        Built discord.Embed.

    Raises:
        EmbedFieldLimitError: If validate_fields=True and 25 fields exceeded.
    """
    # Validate field limit
    if validate_fields:
        field_count = config.count_fields()
        if field_count > 25:
            raise EmbedFieldLimitError(field_count)

    # Determine title (parameter > config)
    embed_title = title
    if embed_title is None and config.title:
        embed_title = format_placeholders(config.title, context)

    # Determine color
    color = _parse_hex_color(config.color) or default_color or discord.Color.blurple()

    embed = discord.Embed(title=embed_title, color=color)

    # Description (appears before fields)
    if config.description:
        embed.description = format_placeholders(config.description, context)

    # Build fields from sections (all sections are fields now)
    for section in config.sections:
        rendered = _render_section(section, context)
        for field_data in rendered["fields"]:
            embed.add_field(
                name=field_data["name"],
                value=field_data["value"],
                inline=field_data["inline"],
            )

    # Thumbnail (skip if placeholder unresolved)
    if config.thumbnail_url:
        url = format_placeholders(config.thumbnail_url, context)
        if "{" not in url:
            embed.set_thumbnail(url=url)

    # Main image (skip if placeholder unresolved)
    if config.image_url:
        url = format_placeholders(config.image_url, context)
        if "{" not in url:
            embed.set_image(url=url)

    # Footer (icon can be shown without text using zero-width space)
    if config.footer_text or config.footer_icon_url:
        footer_text = (
            format_placeholders(config.footer_text, context) if config.footer_text else "\u200b"
        )
        footer_icon = None
        if config.footer_icon_url:
            icon_url = format_placeholders(config.footer_icon_url, context)
            # Only use icon if placeholder was resolved (no { remaining)
            if "{" not in icon_url:
                footer_icon = icon_url
        embed.set_footer(text=footer_text, icon_url=footer_icon)

    return embed


def build_embeds(
    config: EmbedConfig,
    context: PlaceholderContext,
    *,
    title: str | None = None,
    default_color: discord.Color | None = None,
) -> list[discord.Embed]:
    """Build an embed from a section configuration.

    All sections are rendered as Discord fields. This function
    returns a list for compatibility with existing code,
    but always returns a single embed (no auto-split anymore).

    Args:
        config: Embed configuration with sections.
        context: Context with data for resolving placeholders.
        title: Optional title (overrides config.title).
        default_color: Default color if no color in config.

    Returns:
        List with a single built discord.Embed.
    """
    embed = build_embed(
        config,
        context,
        title=title,
        default_color=default_color,
        validate_fields=False,  # Don't validate here, caller can validate if needed
    )
    return [embed]


def build_embed_from_rows(
    rows: list[dict[str, Any]],
    context: PlaceholderContext,
    *,
    title: str | None = None,
    color: str | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
    footer_text: str | None = None,
    footer_icon_url: str | None = None,
    default_color: discord.Color | None = None,
    validate_fields: bool = True,
) -> discord.Embed:
    """Build an embed directly from table configuration rows.

    Shortcut for use with ConfigOptionType.TABLE values.

    Args:
        rows: List of rows from the configuration table.
        context: Context with data for resolving placeholders.
        title: Embed title (supports placeholders).
        color: Color in hex format.
        thumbnail_url: Thumbnail URL.
        image_url: Main image URL.
        footer_text: Footer text.
        footer_icon_url: Footer icon URL.
        default_color: Default color if no color.
        validate_fields: If True, raises error if 25 fields exceeded.

    Returns:
        Built discord.Embed.

    Raises:
        EmbedFieldLimitError: If validate_fields=True and 25 fields exceeded.
    """
    config = EmbedConfig.from_table_rows(rows)
    config.title = title
    config.color = color
    config.thumbnail_url = thumbnail_url
    config.image_url = image_url
    config.footer_text = footer_text
    config.footer_icon_url = footer_icon_url

    return build_embed(
        config, context, default_color=default_color, validate_fields=validate_fields
    )
