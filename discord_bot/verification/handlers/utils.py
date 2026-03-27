"""Utilities for verification handlers."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.formatters import build_mod_embed_sections, format_message

if TYPE_CHECKING:
    from discord_bot.verification.models import VerificationRequest
    from discord_bot.verification.service import VerificationService

# API error messages based on status code (422 is handled separately as invalid images)
API_ERROR_MESSAGES: dict[int, str] = {
    401: "API key required or invalid",
    413: "Image exceeds maximum upload size",
    429: "Rate limit exceeded",
    500: "Internal processing error",
}


def calculate_expires_timestamp(created_at: datetime, timeout_minutes: int) -> str:
    """Calculate expiration timestamp for the {expires} placeholder.

    Args:
        created_at: Request creation date.
        timeout_minutes: Configured timeout minutes.

    Returns:
        Discord relative timestamp (e.g.: "<t:1234567890:R>") or empty string
        if timeout is disabled (0).
    """
    if timeout_minutes <= 0:
        return ""
    expires_at = created_at + timedelta(minutes=timeout_minutes)
    return f"<t:{int(expires_at.timestamp())}:R>"


def get_api_error_message(status_code: int) -> str:
    """Get human-readable error message for API status code.

    Args:
        status_code: HTTP status code from API

    Returns:
        Error message string
    """
    if status_code in API_ERROR_MESSAGES:
        return API_ERROR_MESSAGES[status_code]
    return f"API Error (code: {status_code})"


def create_screenshot_embeds(url1: str | None, url2: str | None) -> list[discord.Embed]:
    """Create embeds to display screenshots.

    Creates embeds with the same base URL so Discord displays them
    as thumbnails in a row instead of stacked large images.

    Args:
        url1: URL of the first screenshot
        url2: URL of the second screenshot

    Returns:
        List of embeds with the images
    """
    embeds = []
    # Use a common URL so Discord displays images in a row
    # This is a Discord trick: embeds with the same url are grouped visually
    common_url = "https://discord.com"

    if url1:
        embed1 = discord.Embed(url=common_url)
        embed1.set_image(url=url1)
        embeds.append(embed1)

    if url2:
        embed2 = discord.Embed(url=common_url)
        embed2.set_image(url=url2)
        embeds.append(embed2)

    return embeds


def get_ready_for_approval_status(
    config: dict[str, Any],
    guild: discord.Guild,
) -> str:
    """Get the 'ready for approval' status text including roles.

    Args:
        config: Cog configuration
        guild: Guild to get roles from

    Returns:
        Formatted status text
    """
    mod_role_ids = config.get(ConfigKey.MOD_ROLES) or []
    role_mentions = []

    for role_id in mod_role_ids:
        role = guild.get_role(role_id)
        if role:
            role_mentions.append(role.mention)

    roles_text = ", ".join(role_mentions) if role_mentions else "moderators"

    status_template = config.get(ConfigKey.STATUS_READY_FOR_APPROVAL) or ""
    return format_message(status_template, roles=roles_text)


async def get_embed_additional_sections(
    request: "VerificationRequest",
    config: dict[str, Any],
    verification_service: "VerificationService",
    player_info: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Get additional sections (player info + history) for the embed.

    Args:
        request: Verification request
        config: Cog configuration
        verification_service: Verification service
        player_info: Player info (if None, reads from request.player_info)

    Returns:
        Tuple of (additional_sections, sections_context)
    """
    if player_info is None:
        player_info = request.player_info

    history = await verification_service.get_user_history(
        guild_id=request.guild_id,
        user_id=request.user_id,
    )
    past_requests = [r for r in history if r.id != request.id]

    return build_mod_embed_sections(
        config=config,
        player_info=player_info,
        past_requests=past_requests,
    )
