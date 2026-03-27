"""Utilities for Discord operations."""

import logging

import discord

logger = logging.getLogger(__name__)

# Valid domains for Discord CDN URLs
DISCORD_CDN_DOMAINS: frozenset[str] = frozenset(
    {
        "cdn.discordapp.com",
        "media.discordapp.net",
    }
)


def is_valid_discord_cdn_url(url: str) -> bool:
    """Verify that a URL is from Discord CDN.

    Args:
        url: URL to verify

    Returns:
        True if it is a valid Discord CDN URL
    """
    if not url:
        return False

    if not url.startswith("https://"):
        return False

    # Extract domain (URL format: https://domain/path)
    domain_part = url[8:]  # Remove "https://"
    domain = domain_part.split("/")[0]
    return domain in DISCORD_CDN_DOMAINS


async def delete_message(
    guild: discord.Guild,
    channel_id: int,
    message_id: int,
) -> bool:
    """Delete a message from a channel.

    Args:
        guild (discord.Guild): Guild where the message is located
        channel_id (int): Channel ID
        message_id (int): Message ID

    Returns:
        bool: True if deleted, False if it could not be deleted
    """
    channel = guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return False

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
        logger.info(f"[{guild.name}] Message deleted from #{channel.name}")
        return True
    except discord.NotFound:
        return False
    except discord.Forbidden:
        logger.warning(f"[{guild.name}] No permissions to delete message in #{channel.name}")
        return False


def has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    """Check if a member has any of the specified roles.

    If the role list is empty, checks for manage_guild permission.

    Args:
        member (discord.Member): Member to check
        role_ids (list[int]): Role IDs to check

    Returns:
        bool: True if they have any of the roles or manage_guild if list is empty
    """
    if not role_ids:
        return member.guild_permissions.manage_guild
    return any(role.id in role_ids for role in member.roles)
