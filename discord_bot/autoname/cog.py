"""Autoname cog for automatic nickname formatting."""

import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands, tasks

from discord_bot.autoname.config import AUTONAME_CONFIG_SCHEMA, COG_NAME, ConfigKey
from discord_bot.autoname.service import compute_nickname
from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class AutonameCog(commands.Cog):
    """Cog for automatic nickname formatting based on roles."""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the autoname cog.

        Args:
            bot (DiscordBot): Bot instance
        """
        self.bot = bot
        self._last_sync: dict[int, datetime] = {}
        self._sync_started = False

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Get options locked by deployment configuration.

        Returns:
            dict[str, dict[str, Any]]: Map of key -> {locked, reason}
        """
        return {}

    async def cog_load(self) -> None:
        """Start tasks when loading the cog."""
        if not self._sync_started:
            self.sync_loop.start()
            self._sync_started = True

    async def cog_unload(self) -> None:
        """Stop tasks when unloading the cog."""
        if self._sync_started:
            self.sync_loop.cancel()
            self._sync_started = False

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Check if the cog is enabled for a guild.

        Args:
            guild_id (int): Guild ID

        Returns:
            bool: True if the cog is enabled
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Get all cog configuration for a guild.

        Args:
            guild_id (int): Guild ID

        Returns:
            dict[str, Any]: Cog configuration
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_sync_interval(self, guild_id: int) -> int:
        """Get the configured sync interval for a guild.

        Args:
            guild_id (int): Guild ID

        Returns:
            int: Interval in minutes (0 if disabled, 30 by default)
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)

            if not await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME):
                return 0

            interval = await config_service.get_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.SYNC_INTERVAL,
            )
            return interval if interval is not None else 30

    async def _send_log(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        message_key: str,
        **placeholders: str,
    ) -> None:
        """Send message to the log channel if configured.

        Args:
            guild (discord.Guild): Guild where to send the log
            config (dict[str, Any]): Cog configuration
            message_key (str): Message key in the config
            **placeholders (str): Values to replace in the message
        """
        channel_id = config.get(ConfigKey.LOG_CHANNEL)
        if not channel_id:
            return

        message_template = config.get(message_key, "")
        if not message_template:
            return

        try:
            channel_id_int = int(channel_id)
            channel = guild.get_channel(channel_id_int)
            if channel and isinstance(channel, discord.TextChannel):
                message = message_template.format(**placeholders)
                await channel.send(message)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"[{guild.name}] Error formatting log message: {e}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Error sending log to channel: {e}")

    async def apply_nickname(self, member: discord.Member) -> bool:
        """Apply formatted nickname to a member.

        Args:
            member (discord.Member): Member to update

        Returns:
            bool: True if the nickname was updated
        """
        if member.bot:
            return False

        config = await self._get_config(member.guild.id)

        # Check required roles if configured
        required_roles = config.get(ConfigKey.REQUIRED_ROLES) or []
        if required_roles:
            member_role_ids_set = {r.id for r in member.roles}
            has_required_role = False
            for role_id in required_roles:
                try:
                    if int(role_id) in member_role_ids_set:
                        has_required_role = True
                        break
                except (ValueError, TypeError):
                    continue
            if not has_required_role:
                return False

        tags_config = config.get(ConfigKey.ROLE_TAGS) or []
        prefixes_config = config.get(ConfigKey.ROLE_PREFIXES) or []
        tag_format = config.get(ConfigKey.TAG_FORMAT) or "[ABC | {tag}]"

        if not tags_config and not prefixes_config:
            return False

        member_role_ids = [r.id for r in member.roles]

        new_nickname = compute_nickname(
            display_name=member.display_name,
            current_nick=member.nick,
            member_role_ids=member_role_ids,
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=tag_format,
        )

        if new_nickname is None:
            return False

        # Safety check - don't update if nickname is already correct
        # (handles edge cases with unicode normalization, whitespace, etc.)
        if new_nickname == member.nick or new_nickname == member.display_name:
            return False

        # Save original name before edit for logging
        original_name = member.display_name

        try:
            await member.edit(nick=new_nickname)
            logger.info(f"[{member.guild.name}] '{original_name}' -> '{new_nickname}'")
            await self._send_log(
                guild=member.guild,
                config=config,
                message_key=ConfigKey.LOG_MESSAGE_SUCCESS,
                old_name=original_name,
                new_name=new_nickname,
            )
            return True
        except discord.Forbidden:
            logger.warning(f"[{member.guild.name}] No permission for '{original_name}'")
            await self._send_log(
                guild=member.guild,
                config=config,
                message_key=ConfigKey.LOG_MESSAGE_NO_PERMS,
                name=original_name,
            )
            return False
        except discord.HTTPException as e:
            logger.error(f"[{member.guild.name}] Error with '{original_name}': {e}")
            return False

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Handle member updates to detect role changes.

        Args:
            before (discord.Member): Previous member state
            after (discord.Member): Current member state
        """
        # Only process if roles changed
        if before.roles == after.roles:
            return

        # Check if the cog is enabled
        if not await self._is_cog_enabled(after.guild.id):
            return

        await self.apply_nickname(after)

    @tasks.loop(minutes=1)
    async def sync_loop(self) -> None:
        """Periodic nickname sync loop.

        Each guild has its own configured interval. This loop runs
        every minute and checks if each guild is ready to sync.
        """
        await self._run_sync()

    @sync_loop.before_loop
    async def before_sync(self) -> None:
        """Wait for the bot to be ready before starting sync."""
        await self.bot.wait_until_ready()
        # Execute immediately on startup
        await self._run_sync(force_all=True)

    async def _run_sync(self, force_all: bool = False) -> None:
        """Run nickname sync on guilds that are ready.

        Args:
            force_all (bool): If True, execute for all guilds ignoring intervals
        """
        now = datetime.now(UTC)

        for guild in self.bot.guilds:
            try:
                interval = await self._get_sync_interval(guild.id)

                if interval == 0:
                    continue

                if not force_all:
                    last_sync = self._last_sync.get(guild.id)
                    if last_sync:
                        seconds_since_last = (now - last_sync).total_seconds()
                        if seconds_since_last < interval * 60:
                            continue

                await self._sync_guild(guild)
                self._last_sync[guild.id] = now

            except Exception as e:
                logger.error(f"[{guild.name}] Error in sync: {e}")

    async def _sync_guild(self, guild: discord.Guild) -> None:
        """Sync nicknames of all members in a guild.

        Args:
            guild (discord.Guild): Guild to sync
        """
        if not await self._is_cog_enabled(guild.id):
            return

        config = await self._get_config(guild.id)
        tags_config = config.get(ConfigKey.ROLE_TAGS) or []
        prefixes_config = config.get(ConfigKey.ROLE_PREFIXES) or []

        if not tags_config and not prefixes_config:
            return

        updated = 0
        for member in guild.members:
            if member.bot:
                continue

            try:
                if await self.apply_nickname(member):
                    updated += 1
            except Exception as e:
                logger.error(
                    "Error applying nickname to '%s' in '%s': %s",
                    member.display_name,
                    guild.name,
                    e,
                )

        if updated > 0:
            logger.info(f"[{guild.name}] Autoname sync: {updated} nicknames updated")

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Handle when the cog is enabled or disabled.

        Args:
            guild (discord.Guild): Guild where the state changed
            enabled (bool): True if enabled, False if disabled
        """
        if enabled:
            logger.info(f"[{guild.name}] Autoname enabled, syncing nicknames")
            await self._sync_guild(guild)
        else:
            logger.info(f"[{guild.name}] Autoname disabled")

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Callback when the cog configuration changes.

        Args:
            guild (discord.Guild): Guild where config changed
            keys (list[str]): List of configuration keys that changed
        """
        # Re-sync if role, prefix, format or required role configuration changes
        resync_keys = {
            ConfigKey.ROLE_TAGS,
            ConfigKey.ROLE_PREFIXES,
            ConfigKey.TAG_FORMAT,
            ConfigKey.REQUIRED_ROLES,
        }
        if set(keys) & resync_keys:
            changed = set(keys) & resync_keys
            logger.info(f"[{guild.name}] Configuration {changed} changed, re-syncing")
            await self._sync_guild(guild)


async def setup(bot: DiscordBot) -> None:
    """Load the autoname cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().register_schema(AUTONAME_CONFIG_SCHEMA)
    await bot.add_cog(AutonameCog(bot))


async def teardown(bot: DiscordBot) -> None:
    """Unload the autoname cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().unregister_schema(COG_NAME)
