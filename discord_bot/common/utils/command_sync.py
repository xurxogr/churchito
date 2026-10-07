"""Sync a guild's slash commands with Discord and report failures.

Cogs that register per-guild commands all need the same thing after a
registration change: push the tree to Discord, log the outcome, and let the
caller decide whether a failure matters. Dashboard callbacks propagate the
error so the admin sees it; startup paths only log it and move on.

Requests for the same guild that arrive within ``SYNC_COALESCE_DELAY`` seconds
share one push. At startup every cog registers its commands and asks for a
sync almost at once; pushing per cog hits Discord's per-guild rate limit (the
second overwrite waits a minute) and briefly publishes a tree that is missing
the cogs that have not registered yet.
"""

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

# Seconds to wait for other cogs before pushing a guild's tree to Discord.
SYNC_COALESCE_DELAY = 1.5


class CommandSyncError(Exception):
    """Discord rejected a guild command sync; the message is safe to show to admins."""


class _PendingSync:
    """A guild sync that is waiting for the coalescing window to close."""

    def __init__(self) -> None:
        self.future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.labels: list[str] = []


# One pending sync per (tree, guild); the task that runs it removes the entry.
_pending: dict[tuple[int, int], _PendingSync] = {}


async def sync_guild_commands(
    *,
    tree: app_commands.CommandTree[Any],
    guild: discord.Guild,
    label: str,
) -> None:
    """Sync the command tree for a guild, sharing the push with overlapping requests.

    Args:
        tree (app_commands.CommandTree[Any]): Bot command tree.
        guild (discord.Guild): Guild to sync.
        label (str): Cog label for log lines and the error message (e.g. "stockpile").

    Raises:
        CommandSyncError: If Discord rejects the sync; the original error is chained.
    """
    key = (id(tree), guild.id)
    pending = _pending.get(key)
    if pending is None:
        pending = _PendingSync()
        _pending[key] = pending
        asyncio.create_task(_run_pending_sync(key=key, pending=pending, tree=tree, guild=guild))
    pending.labels.append(label)
    await asyncio.shield(pending.future)


async def _run_pending_sync(
    *,
    key: tuple[int, int],
    pending: _PendingSync,
    tree: app_commands.CommandTree[Any],
    guild: discord.Guild,
) -> None:
    """Wait for the coalescing window, then push the guild's tree once.

    Args:
        key (tuple[int, int]): Entry in the pending table to release.
        pending (_PendingSync): Shared future and labels of the coalesced callers.
        tree (app_commands.CommandTree[Any]): Bot command tree.
        guild (discord.Guild): Guild to sync.
    """
    try:
        await asyncio.sleep(SYNC_COALESCE_DELAY)
    except asyncio.CancelledError:
        pending.future.set_exception(CommandSyncError("Command sync cancelled before it ran"))
        raise
    finally:
        # From here on new requests start their own sync instead of joining this one.
        _pending.pop(key, None)

    label = "+".join(pending.labels)
    try:
        await tree.sync(guild=guild)
    except Exception as e:
        logger.error(f"[{guild.name}] Error syncing {label} commands: {e}")
        error = CommandSyncError(f"Could not sync {label} commands with Discord: {e}")
        error.__cause__ = e
        pending.future.set_exception(error)
        return
    logger.info(f"[{guild.name}] {label.capitalize()} commands synced")
    pending.future.set_result(None)
