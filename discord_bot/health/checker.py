"""Keep the running bot consistent with its config and with Discord.

Three things can drift apart while the process runs: the cogs the config
enables versus the extensions actually loaded, the commands each cog believes
it registered versus the command tree, and the tree versus what Discord has
published for each guild. A cog reload or a failed startup leaves any of them
out of step, and users only notice when a command stops answering. The checker
compares all three on a fixed cadence and repairs what it finds, so recovery
does not depend on anyone pressing a button.
"""

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import discord

from discord_bot.common.utils.command_sync import CommandSyncError, sync_guild_commands

if TYPE_CHECKING:
    from discord_bot.bot import DiscordBot

logger = logging.getLogger(__name__)

# Seconds before a guild still out of sync after a repair gets another one.
# A persistent mismatch would otherwise push the tree on every pass and burn
# Discord's per-guild command budget.
REPAIR_COOLDOWN = 3600.0


class HealthChecker:
    """Periodic, process-wide consistency check with self-repair."""

    def __init__(self, *, bot: "DiscordBot") -> None:
        """Create a checker bound to a bot.

        Args:
            bot (DiscordBot): Running bot whose state is checked.
        """
        self.bot = bot
        self._repaired_at: dict[int, float] = {}

    async def run(self) -> None:
        """Run ``check_all`` every configured interval until cancelled."""
        interval = self.bot.settings.health.interval_seconds
        logger.info(f"Health check started (every {interval:.0f}s)")
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.check_all()
                except Exception as e:
                    logger.error(f"Health check pass failed: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("Health check stopped")
            raise

    async def check_all(self) -> None:
        """Check extensions and every guild, isolating failures per guild."""
        if not self.bot.is_ready():
            logger.debug("Health check skipped: bot not ready")
            return

        await self._ensure_extensions_loaded()

        for guild in list(self.bot.guilds):
            try:
                await self.check_guild(guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Health check failed: {e}", exc_info=True)

    async def _ensure_extensions_loaded(self) -> None:
        """Load any extension the config enables but the bot no longer has."""
        for module in self.bot.settings.cogs.enabled_extensions():
            if module in self.bot.extensions:
                continue
            logger.warning(f"Health check: {module} is enabled but not loaded, loading it")
            try:
                await self.bot.load_extension(module)
            except Exception as e:
                logger.error(f"Health check: could not load {module}: {e}", exc_info=True)

    async def check_guild(self, guild: discord.Guild) -> bool:
        """Compare cog bookkeeping, the local tree and Discord for one guild.

        Args:
            guild (discord.Guild): Guild to check.

        Returns:
            bool: True if a repair sync was pushed to Discord.
        """
        await self._let_cogs_recover(guild)

        local = {command.name for command in self.bot.tree.get_commands(guild=guild)}
        try:
            fetched = await self.bot.tree.fetch_commands(guild=guild)
        except Exception as e:
            logger.error(f"[{guild.name}] Health check: could not fetch commands: {e}")
            return False
        remote = {command.name for command in fetched}

        if local == remote:
            self._repaired_at.pop(guild.id, None)
            return False

        missing = sorted(local - remote)
        stale = sorted(remote - local)
        last_repair = self._repaired_at.get(guild.id)
        if last_repair is not None and time.monotonic() - last_repair < REPAIR_COOLDOWN:
            logger.error(
                f"[{guild.name}] Commands still out of sync after a repair "
                f"(missing on Discord: {missing}, stale on Discord: {stale}); "
                "not retrying until the cooldown passes"
            )
            return False

        logger.warning(
            f"[{guild.name}] Commands out of sync with Discord "
            f"(missing on Discord: {missing}, stale on Discord: {stale}), repairing"
        )
        self._repaired_at[guild.id] = time.monotonic()
        with suppress(CommandSyncError):
            await sync_guild_commands(tree=self.bot.tree, guild=guild, label="health")
        return True

    async def _let_cogs_recover(self, guild: discord.Guild) -> None:
        """Ask each cog to put back commands it tracks but the tree lost.

        Args:
            guild (discord.Guild): Guild being checked.
        """
        for cog in list(self.bot.cogs.values()):
            recover = getattr(cog, "recover_guild_commands", None)
            if recover is None:
                continue
            try:
                await recover(guild=guild)
            except Exception as e:
                logger.error(
                    f"[{guild.name}] Health check: {cog.qualified_name} could not recover: {e}"
                )
