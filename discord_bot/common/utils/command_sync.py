"""Sync a guild's slash commands with Discord and report failures.

Cogs that register per-guild commands all need the same thing after a
registration change: push the tree to Discord, log the outcome, and let the
caller decide whether a failure matters. Dashboard callbacks propagate the
error so the admin sees it; startup paths only log it and move on.
"""

import logging
from typing import Any

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


class CommandSyncError(Exception):
    """Discord rejected a guild command sync; the message is safe to show to admins."""


async def sync_guild_commands(
    *,
    tree: app_commands.CommandTree[Any],
    guild: discord.Guild,
    label: str,
) -> None:
    """Sync the command tree for a guild.

    Args:
        tree (app_commands.CommandTree[Any]): Bot command tree.
        guild (discord.Guild): Guild to sync.
        label (str): Cog label for log lines and the error message (e.g. "stockpile").

    Raises:
        CommandSyncError: If Discord rejects the sync; the original error is chained.
    """
    try:
        await tree.sync(guild=guild)
    except Exception as e:
        logger.error(f"[{guild.name}] Error syncing {label} commands: {e}")
        raise CommandSyncError(f"Could not sync {label} commands with Discord: {e}") from e
    logger.info(f"[{guild.name}] {label.capitalize()} commands synced")
