"""Formatting functions for the verification cog."""

from __future__ import annotations

import re
from typing import Any

import discord

from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection
from discord_bot.common.services.embed_builder import (
    PlaceholderContext,
    build_embeds,
)
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType

# Default embed config for moderation
DEFAULT_MOD_EMBED_CONFIG: dict[str, Any] = {
    "color": "#FFA500",
    "description": (
        "**User:** {user_mention} ({username})\n"
        "**Type:** {verification_type}\n"
        "**Date:** {created_at}\n\n"
        "{status}"
    ),
    "sections": [],
}


def format_message(template: str | None = None, **kwargs: str | None) -> str:
    """Replace placeholders in a message.

    Args:
        template (str | None): Message template.
        **kwargs: Placeholders to replace (e.g.: username="John", status="Pending").

    Returns:
        str: Formatted message.
    """
    result = template or ""
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value or "")
    return result


def create_panel_embed(text: str) -> discord.Embed:
    """Create an embed for the verification panel.

    Searches for image URLs in the text and uses them for the embed.
    The image URL is removed from the displayed text.

    Args:
        text (str): Message text that may contain image URLs.

    Returns:
        discord.Embed: Embed with the formatted message.
    """
    # Search for image URLs
    image_pattern = r"(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s]*)?)"
    match = re.search(pattern=image_pattern, string=text, flags=re.IGNORECASE)

    image_url = None
    clean_text = text

    if match:
        image_url = match.group(1)
        # Remove the URL from the text (and extra empty lines)
        clean_text = re.sub(
            pattern=image_pattern, repl="", string=text, count=1, flags=re.IGNORECASE
        )
        clean_text = re.sub(pattern=r"\n{3,}", repl="\n\n", string=clean_text).strip()

    embed = discord.Embed(
        description=clean_text,
        color=discord.Color.blurple(),
    )

    if image_url:
        embed.set_image(url=image_url)

    return embed


def _parse_hex_color(hex_color: str | None) -> discord.Color | None:
    """Parse a hexadecimal color to discord.Color.

    Args:
        hex_color (str | None): Color in hex format (#FF5733 or FF5733).

    Returns:
        discord.Color | None: Parsed color or None if the format is invalid.
    """
    if not hex_color:
        return None
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return discord.Color(int(hex_color, 16))
    except ValueError:
        return None


def build_history_section(
    past_requests: list[Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Build history section for mod embeds.

    Args:
        past_requests (list[Any]): List of past verification requests (excluding current).
        config (dict[str, Any]): Cog configuration.

    Returns:
        dict[str, Any] | None: Section dict for embed, or None if no history.
    """
    if not past_requests:
        return None

    history_label = config.get(ConfigKey.HISTORY_LABEL) or "History"
    history_lines = []

    for past in past_requests[:5]:
        status_emoji = {
            VerificationStatus.APPROVED: "✅",
            VerificationStatus.REJECTED: "❌",
            VerificationStatus.CANCELLED: "🚫",
        }.get(VerificationStatus(past.status), "❓")
        timestamp = past.reviewed_at or past.created_at
        date_str = timestamp.strftime("%Y-%m-%d %H:%M")
        moderator = past.reviewed_by_username or ""
        past_type_display = get_verification_type_display(
            verification_type=VerificationType(past.verification_type), config=config
        )
        line = f"{status_emoji} {past_type_display} - {moderator} ({date_str})"
        if past.rejection_reason:
            line += f" - {past.rejection_reason}"
        history_lines.append(line)

    return {
        "type": "text",
        "title": history_label,
        "content": "\n".join(history_lines),
    }


def build_mod_embed_sections(
    config: dict[str, Any],
    player_info: dict[str, Any] | None,
    past_requests: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Build additional sections and context for mod embeds.

    Args:
        config (dict[str, Any]): Cog configuration.
        player_info (dict[str, Any] | None): OCR player info dict (from DB or API result).
        past_requests (list[Any]): List of past verification requests (excluding current).

    Returns:
        tuple[list[dict[str, Any]], dict[str, Any] | None]: Additional sections and context.
    """
    additional_sections: list[dict[str, Any]] = []
    sections_context: dict[str, Any] | None = None

    # Add player info sections if available
    if player_info:
        player_info_sections = config.get(ConfigKey.PLAYER_INFO_SECTIONS)
        if player_info_sections and isinstance(player_info_sections, list):
            additional_sections = list(player_info_sections)
            sections_context = player_info

    # Add history section
    history_section = build_history_section(
        past_requests=past_requests,
        config=config,
    )
    if history_section:
        additional_sections.append(history_section)

    return additional_sections, sections_context


def create_mod_embeds(
    verification_type: VerificationType,
    config: dict[str, Any],
    *,
    username: str | None = None,
    user_mention: str | None = None,
    user_id: int | None = None,
    status: str | None = None,
    created_at: str | None = None,
    created_at_relative: str | None = None,
    guild: discord.Guild | None = None,
    member: discord.Member | None = None,
    additional_content: str | None = None,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
    **extra_placeholders: str | None,
) -> list[discord.Embed]:
    """Create embeds for the moderation message with auto-split.

    When a description section follows a fields section (or vice versa),
    a new embed is created automatically to maintain visual order.

    Args:
        verification_type (VerificationType): Verification type (REGULAR or ALLY).
        config (dict[str, Any]): Cog configuration with the embed config.
        username (str | None): User's name.
        user_mention (str | None): User mention.
        user_id (int | None): User ID (for thumbnail fallback).
        status (str | None): Current status text.
        created_at (str | None): Formatted creation date (YYYY-MM-DD HH:MM).
        created_at_relative (str | None): Relative creation date (<t:UNIX:R>).
        guild (discord.Guild | None): Discord guild (for global placeholders).
        member (discord.Member | None): Discord member (for user placeholders).
        additional_content (str | None): Additional content (API errors, user history).
        additional_sections (list[dict[str, Any]] | None): Additional sections to add.
        sections_context (dict[str, Any] | None): Placeholder context for sections.
        **extra_placeholders (str | None): Additional placeholders.

    Returns:
        list[discord.Embed]: List of embeds with the formatted message.
    """
    # Get the embed config based on verification type
    if verification_type == VerificationType.REGULAR:
        embed_config_data = config.get(ConfigKey.MOD_EMBED_REGULAR)
    else:
        embed_config_data = config.get(ConfigKey.MOD_EMBED_ALLY)

    # Use default config if no configuration exists
    if not embed_config_data or not isinstance(embed_config_data, dict):
        embed_config_data = DEFAULT_MOD_EMBED_CONFIG

    # Build EmbedConfig from the data
    embed_config = EmbedConfig(**embed_config_data)

    # Get the verification type display name
    type_display = get_verification_type_display(verification_type=verification_type, config=config)

    # Create context with all placeholders
    extra_data: dict[str, Any] = {
        "username": username or "",
        "user_mention": user_mention or "",
        "verification_type": type_display,
        "status": status or "",
        "created_at": created_at or "",
        "created_at_relative": created_at_relative or "",
        **{k: v or "" for k, v in extra_placeholders.items()},
    }

    context = PlaceholderContext(
        guild=guild,
        member=member,
        extra_data=extra_data,
    )

    # Add additional sections to embed config if they exist
    all_sections = list(embed_config.sections)

    if additional_sections:
        # Create combined context for additional sections
        sections_extra_data = dict(extra_data)
        if sections_context:
            sections_extra_data.update(sections_context)

        # Validate and add additional sections
        for section_data in additional_sections:
            if not isinstance(section_data, dict):
                continue
            if not section_data.get("type"):
                continue
            try:
                section = EmbedSection(**section_data)
                all_sections.append(section)
            except (TypeError, ValueError):
                continue

        # Update the context with additional sections data
        context = PlaceholderContext(
            guild=guild,
            member=member,
            extra_data=sections_extra_data,
        )

    # Build the complete EmbedConfig with all sections
    full_config = EmbedConfig(
        title=embed_config.title,
        description=embed_config.description,
        color=embed_config.color,
        thumbnail_url=embed_config.thumbnail_url,
        image_url=embed_config.image_url,
        footer_text=embed_config.footer_text,
        footer_icon_url=embed_config.footer_icon_url,
        sections=all_sections,
    )

    # Build the embeds with auto-split
    embeds = build_embeds(
        config=full_config,
        context=context,
        default_color=discord.Color.orange(),
    )

    # Add additional content (API errors, history) to the last embed
    if additional_content and embeds:
        last_embed = embeds[-1]
        current_desc = last_embed.description or ""
        last_embed.description = current_desc + additional_content

    # Fallback for thumbnail if not configured (first embed)
    if embeds and not embeds[0].thumbnail.url and user_id:
        embeds[0].set_thumbnail(url=f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png")

    return embeds


def get_verification_type_display(
    verification_type: VerificationType, config: dict[str, Any]
) -> str:
    """Get the display name for a verification type.

    Args:
        verification_type (VerificationType): Verification type.
        config (dict[str, Any]): Cog configuration.

    Returns:
        str: Display name.
    """
    if verification_type == VerificationType.REGULAR:
        return config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
    return config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Ally"


def create_tracker_embed(
    pending_requests: list[Any],
    config: dict[str, Any],
    guild_id: int,
    channel_id: int,
) -> discord.Embed:
    """Create embed showing all pending verifications.

    Groups requests by verification type and displays each one
    in compact format: id, username, status and relative time.

    Args:
        pending_requests (list[Any]): List of pending VerificationRequest.
        config (dict[str, Any]): Cog configuration.
        guild_id (int): Guild ID for building links.
        channel_id (int): Moderation channel ID for building links.

    Returns:
        discord.Embed: Embed with the list of pending verifications.
    """
    title = config.get(ConfigKey.TRACKER_TITLE) or "📋 Pending Verifications"
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue(),
    )

    # Group requests by verification type
    grouped: dict[str, list[Any]] = {}
    for request in pending_requests:
        v_type = request.verification_type
        if v_type not in grouped:
            grouped[v_type] = []
        grouped[v_type].append(request)

    sections = []
    for v_type, requests in grouped.items():
        # Get type display name for header
        verification_type = VerificationType(v_type)
        type_display = get_verification_type_display(
            verification_type=verification_type, config=config
        )

        lines = [f"**{type_display}**"]
        for request in requests:
            # Get status text
            if request.status == VerificationStatus.PENDING_SCREENSHOTS:
                status_text = (
                    config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "Awaiting screenshots"
                )
            else:
                status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "Pending review"
            status_text = _clean_status_text(status_text)

            # Discord relative timestamp
            unix_timestamp = int(request.created_at.timestamp())
            relative_time = f"<t:{unix_timestamp}:R>"

            # Link to moderation message using verification public_id
            if request.mod_message_id:
                message_link = (
                    f"https://discord.com/channels/{guild_id}/{channel_id}/{request.mod_message_id}"
                )
                id_text = f"[#{request.public_id}]({message_link})"
            else:
                id_text = f"#{request.public_id}"

            # Compact line: id username - status - time
            line = f"{id_text} {request.username} - {status_text} - {relative_time}"
            lines.append(line)

        sections.append("\n".join(lines))

    embed.description = "\n\n".join(sections)
    return embed


def _clean_status_text(status_text: str) -> str:
    """Clean status text by removing emojis and bold formatting.

    Args:
        status_text (str): Status text from config (may include emoji and markdown).

    Returns:
        str: Clean text without leading emojis or formatting.
    """
    # Remove emoji at the start
    cleaned = re.sub(r"^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\s]+", "", status_text)
    # Remove **Status:** or similar
    cleaned = re.sub(r"\*\*[^*]+:\*\*\s*", "", cleaned)
    return cleaned.strip()
