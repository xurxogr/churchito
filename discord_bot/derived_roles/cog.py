"""Derived roles cog for automatic role dependencies."""

import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.services.cog_config_cache import CogConfigCache
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.utils import BackgroundTasks, GuildScheduler, KeyedLocks
from discord_bot.derived_roles.config import COG_NAME, DERIVED_ROLES_CONFIG_SCHEMA, ConfigKey
from discord_bot.derived_roles.engine import compute_role_changes
from discord_bot.derived_roles.formatters import format_message

logger = logging.getLogger(__name__)

ROLE_CHANGE_REASON = "Derived roles"


class DerivedRolesCog(commands.Cog):
    """Cog that keeps role dependencies in sync.

    Applies state-based rules (grants, requires, forbids) whenever a
    member's roles change and through a periodic reconciliation sweep.
    """

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the derived roles cog.

        Args:
            bot (DiscordBot): Bot instance
        """
        self.bot = bot
        # Per-guild next-due times, so idle minute ticks read no configuration
        self._schedule = GuildScheduler()
        self._sync_started = False
        # Full-guild reconciliations triggered from the dashboard run here, so
        # the web request returns immediately instead of waiting on role edits
        self._background = BackgroundTasks(logger=logger)
        # Guilds with a reconciliation in progress (a second one would only repeat it)
        self._syncing_guilds: set[int] = set()
        # Per-member locks to avoid concurrent rule application
        self._member_locks = KeyedLocks()
        # Guilds currently in permission-error state (notify on state change only)
        self._error_state: dict[int, bool] = {}
        # Per-guild enabled flag + config, so member updates do not open a
        # database session per event
        self._config_cache = CogConfigCache(database=bot.database, cog_name=COG_NAME)

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
        self._background.cancel_all()

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Check if the cog is enabled for a guild (cached).

        Args:
            guild_id (int): Guild ID

        Returns:
            bool: True if the cog is enabled
        """
        return (await self._config_cache.get(guild_id)).enabled

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Get all cog configuration for a guild (cached).

        Args:
            guild_id (int): Guild ID

        Returns:
            dict[str, Any]: Cog configuration
        """
        return (await self._config_cache.get(guild_id)).config

    # ===== EVENT HANDLERS =====

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Drop cached per-guild state when the bot leaves a guild.

        Args:
            guild (discord.Guild): Guild the bot left.
        """
        self._schedule.reset(guild.id)
        self._error_state.pop(guild.id, None)
        self._config_cache.invalidate(guild.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Handle member updates to detect role changes.

        Args:
            before (discord.Member): Previous member state
            after (discord.Member): Current member state
        """
        if before.roles == after.roles:
            return

        if after.bot:
            return

        if not await self._is_cog_enabled(after.guild.id):
            return

        before_ids = {role.id for role in before.roles}
        after_ids = {role.id for role in after.roles}
        trigger_gained = [role for role in after.roles if role.id not in before_ids]
        trigger_lost = [role for role in before.roles if role.id not in after_ids]

        config = await self._get_config(after.guild.id)
        await self._apply_rules(
            member=after,
            config=config,
            trigger_gained=trigger_gained,
            trigger_lost=trigger_lost,
        )

    # ===== RULE APPLICATION =====

    async def _apply_rules(
        self,
        member: discord.Member,
        config: dict[str, Any],
        trigger_gained: list[discord.Role] | None = None,
        trigger_lost: list[discord.Role] | None = None,
    ) -> bool:
        """Apply derived role rules to a member.

        Args:
            member (discord.Member): Member to process
            config (dict[str, Any]): Cog configuration
            trigger_gained (list[discord.Role] | None): Roles gained in the event
                that triggered this evaluation, None for reconciliation sweeps
            trigger_lost (list[discord.Role] | None): Roles lost in the event
                that triggered this evaluation, None for reconciliation sweeps

        Returns:
            bool: True if any role was changed
        """
        rules = config.get(ConfigKey.RULES) or []
        if not rules:
            return False

        guild = member.guild
        async with self._member_locks.acquire(member.id):
            member_role_ids = {r.id for r in member.roles}
            to_add, to_remove = compute_role_changes(member_role_ids=member_role_ids, rules=rules)

            if not to_add and not to_remove:
                return False

            add_roles = self._resolve_roles(guild=guild, role_ids=to_add)
            remove_roles = self._resolve_roles(guild=guild, role_ids=to_remove)

            if not add_roles and not remove_roles:
                return False

            try:
                # Remove first: removal wins semantics, and faction switches
                # should drop the old roles before granting new ones
                if remove_roles:
                    await member.remove_roles(*remove_roles, reason=ROLE_CHANGE_REASON)
                if add_roles:
                    await member.add_roles(*add_roles, reason=ROLE_CHANGE_REASON)
            except discord.Forbidden:
                await self._notify_error(guild=guild, config=config, member=member)
                return False
            except discord.HTTPException as e:
                logger.error(
                    f"[{guild.name}] Error applying derived roles to '{member.display_name}': {e}"
                )
                return False

            logger.info(
                f"[{guild.name}] Derived roles for '{member.display_name}': "
                f"trigger gained {[r.name for r in trigger_gained or []]}, "
                f"lost {[r.name for r in trigger_lost or []]}; "
                f"added {[r.name for r in add_roles]}, removed {[r.name for r in remove_roles]}"
            )
            await self._notify_recovered(guild=guild, config=config)
            await self._notify_applied(
                guild=guild,
                config=config,
                member=member,
                added=add_roles,
                removed=remove_roles,
                trigger_gained=trigger_gained or [],
                trigger_lost=trigger_lost or [],
            )
            return True

    def _resolve_roles(self, guild: discord.Guild, role_ids: set[int]) -> list[discord.Role]:
        """Resolve role IDs to role objects, logging missing ones.

        Args:
            guild (discord.Guild): Discord guild
            role_ids (set[int]): Role IDs to resolve

        Returns:
            list[discord.Role]: Resolved roles
        """
        roles: list[discord.Role] = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role:
                roles.append(role)
            else:
                logger.warning(f"[{guild.name}] Derived roles: role {role_id} not found")
        return roles

    # ===== AUDIT NOTIFICATIONS =====

    async def _notify_applied(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        member: discord.Member,
        added: list[discord.Role],
        removed: list[discord.Role],
        trigger_gained: list[discord.Role],
        trigger_lost: list[discord.Role],
    ) -> None:
        """Send audit notification for an applied rule change.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
            member (discord.Member): Affected member
            added (list[discord.Role]): Roles added
            removed (list[discord.Role]): Roles removed
            trigger_gained (list[discord.Role]): Roles gained in the triggering event
            trigger_lost (list[discord.Role]): Roles lost in the triggering event
        """
        if not config.get(ConfigKey.AUDIT_APPLIED):
            return

        added_text = ", ".join(role.mention for role in added) or "—"
        removed_text = ", ".join(role.mention for role in removed) or "—"
        trigger_parts = [f"+{role.mention}" for role in trigger_gained] + [
            f"-{role.mention}" for role in trigger_lost
        ]
        trigger_text = ", ".join(trigger_parts) or "—"
        await self._send_audit(
            guild=guild,
            config=config,
            template_key=ConfigKey.AUDIT_APPLIED_MSG,
            user_name=member.display_name,
            user_mention=member.mention,
            added_roles=added_text,
            removed_roles=removed_text,
            trigger_changes=trigger_text,
        )

    async def _notify_error(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        member: discord.Member,
    ) -> None:
        """Handle a permission failure, notifying only on state change.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
            member (discord.Member): Member whose roles could not be modified
        """
        logger.warning(
            f"[{guild.name}] Cannot modify derived roles for '{member.display_name}' "
            f"(missing permissions or role hierarchy)"
        )

        was_in_error = self._error_state.get(guild.id, False)
        self._error_state[guild.id] = True
        if was_in_error:
            return

        if not config.get(ConfigKey.AUDIT_ERROR):
            return

        await self._send_audit(
            guild=guild,
            config=config,
            template_key=ConfigKey.AUDIT_ERROR_MSG,
            user_name=member.display_name,
            user_mention=member.mention,
        )

    async def _notify_recovered(self, guild: discord.Guild, config: dict[str, Any]) -> None:
        """Notify recovery after a previous error state.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
        """
        if not self._error_state.get(guild.id, False):
            return

        self._error_state[guild.id] = False
        logger.info(f"[{guild.name}] Derived roles: role management recovered")

        if not config.get(ConfigKey.AUDIT_ERROR):
            return

        await self._send_audit(
            guild=guild,
            config=config,
            template_key=ConfigKey.AUDIT_RECOVERED_MSG,
        )

    async def _send_audit(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        template_key: str,
        **placeholders: str,
    ) -> None:
        """Format and send a message to the audit channel if configured.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
            template_key (str): Config key of the message template
            **placeholders (str): Values to replace in the template
        """
        channel_id = config.get(ConfigKey.AUDIT_CHANNEL)
        if not channel_id:
            return

        template = config.get(template_key)
        if not template:
            return

        message = format_message(template=template, **placeholders)

        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot send to derived roles audit channel")
        except discord.HTTPException as e:
            logger.error(f"[{guild.name}] Error sending audit message: {e}")

    # ===== RECONCILIATION =====

    @tasks.loop(minutes=1)
    async def sync_loop(self) -> None:
        """Periodic reconciliation loop.

        Each guild has its own configured interval. This loop runs every
        minute and checks if each guild is ready to sync.
        """
        await self._run_sync()

    @sync_loop.before_loop
    async def before_sync(self) -> None:
        """Wait for the bot to be ready before starting sync."""
        await self.bot.wait_until_ready()
        # Execute immediately on startup to repair state missed while offline
        await self._run_sync(force_all=True)

    async def _run_sync(self, force_all: bool = False) -> None:
        """Run reconciliation on guilds that are ready.

        Args:
            force_all (bool): If True, execute for all guilds ignoring intervals
        """
        now = datetime.now(UTC)

        for guild in self.bot.guilds:
            try:
                if not force_all and not self._schedule.is_due(guild_id=guild.id, now=now):
                    continue

                if not await self._is_cog_enabled(guild.id):
                    self._schedule.defer(guild_id=guild.id, now=now)
                    continue

                config = await self._get_config(guild.id)
                interval = config.get(ConfigKey.SYNC_INTERVAL)
                interval = interval if interval is not None else 60

                if interval == 0:
                    self._schedule.defer(guild_id=guild.id, now=now)
                    continue

                await self._sync_guild(guild=guild, config=config)
                self._schedule.mark_run(guild_id=guild.id, now=now, interval_minutes=interval)

            except Exception as e:
                logger.error(f"[{guild.name}] Error in derived roles sync: {e}")

    async def _sync_guild(self, guild: discord.Guild, config: dict[str, Any]) -> None:
        """Reconcile all members of a guild against the rules.

        Skipped when a reconciliation for the guild is already running: the
        periodic loop and a dashboard change can both ask for one at nearly
        the same time, and a second pass would only repeat the first.

        Args:
            guild (discord.Guild): Guild to reconcile
            config (dict[str, Any]): Cog configuration
        """
        if guild.id in self._syncing_guilds:
            logger.debug(f"[{guild.name}] Derived roles sync already running, skipping")
            return
        self._syncing_guilds.add(guild.id)
        try:
            await self._sync_members(guild=guild, config=config)
        finally:
            self._syncing_guilds.discard(guild.id)

    def _sync_guild_in_background(self, guild: discord.Guild) -> None:
        """Load the guild configuration and reconcile members without blocking the caller.

        Args:
            guild (discord.Guild): Guild to reconcile
        """
        self._background.spawn(
            self._load_and_sync_guild(guild), name=f"derived-roles-sync-{guild.id}"
        )

    async def _load_and_sync_guild(self, guild: discord.Guild) -> None:
        """Reconcile a guild with its current configuration.

        Args:
            guild (discord.Guild): Guild to reconcile
        """
        config = await self._get_config(guild.id)
        await self._sync_guild(guild=guild, config=config)

    async def _sync_members(self, guild: discord.Guild, config: dict[str, Any]) -> None:
        """Apply the rules to every member of a guild.

        Args:
            guild (discord.Guild): Guild to reconcile
            config (dict[str, Any]): Cog configuration
        """
        rules = config.get(ConfigKey.RULES) or []
        if not rules:
            return

        corrected = 0
        for member in guild.members:
            if member.bot:
                continue

            try:
                if await self._apply_rules(member=member, config=config):
                    corrected += 1
            except Exception as e:
                logger.error(
                    "Error applying derived roles to '%s' in '%s': %s",
                    member.display_name,
                    guild.name,
                    e,
                )

        if corrected > 0:
            logger.info(f"[{guild.name}] Derived roles sync: {corrected} member(s) corrected")
            if config.get(ConfigKey.AUDIT_RECONCILIATION):
                await self._send_audit(
                    guild=guild,
                    config=config,
                    template_key=ConfigKey.AUDIT_RECONCILIATION_MSG,
                    count=str(corrected),
                )

    # ===== CONFIG CHANGE CALLBACKS =====

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Handle when the cog is enabled or disabled.

        Args:
            guild (discord.Guild): Guild where the state changed
            enabled (bool): True if enabled, False if disabled
        """
        self._config_cache.invalidate(guild.id)
        self._schedule.reset(guild.id)
        if enabled:
            logger.info(f"[{guild.name}] Derived roles enabled, reconciling members")
            self._sync_guild_in_background(guild)
        else:
            logger.info(f"[{guild.name}] Derived roles disabled")

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Callback when the cog configuration changes.

        Args:
            guild (discord.Guild): Guild where config changed
            keys (list[str]): List of configuration keys that changed
        """
        self._config_cache.invalidate(guild.id)
        self._schedule.reset(guild.id)
        if ConfigKey.RULES in set(keys):
            logger.info(f"[{guild.name}] Derived roles rules changed, reconciling members")
            self._sync_guild_in_background(guild)


async def setup(bot: DiscordBot) -> None:
    """Load the derived roles cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().register_schema(DERIVED_ROLES_CONFIG_SCHEMA)
    await bot.add_cog(DerivedRolesCog(bot))


async def teardown(bot: DiscordBot) -> None:
    """Unload the derived roles cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().unregister_schema(COG_NAME)
