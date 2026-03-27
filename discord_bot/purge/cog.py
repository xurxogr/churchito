"""Purge cog for member activity management."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.purge.config import COG_NAME, PURGE_CONFIG_SCHEMA
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.execution import execute_purge
from discord_bot.purge.formatters import (
    format_message,
    format_roles,
    get_button_style,
    get_mod_message_content,
)
from discord_bot.purge.models import PurgeRecord
from discord_bot.purge.service import PurgeService
from discord_bot.purge.settings import get_purge_settings
from discord_bot.purge.views import ModAuthorizationView, UserConfirmationView

logger = logging.getLogger(__name__)


class PurgeCog(commands.Cog):
    """Cog for member purge management."""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the cog.

        Args:
            bot (DiscordBot): Discord bot instance.
        """
        self.bot = bot
        # Track registered commands per guild and type: {guild_id: {"war": name, "global": name}}
        self._registered_commands: dict[int, dict[str, str]] = {}
        # Debounce pending syncs: {guild_id: asyncio.Task}
        self._pending_syncs: dict[int, asyncio.Task[None]] = {}
        # Debounce delay in seconds
        self._sync_debounce_delay = 2.0
        # Track active purges in memory: {guild_id: (purge_id, expires_at)}
        self._active_purges: dict[int, tuple[int, datetime | None]] = {}
        # Track authorized purges for execution: {guild_id: (purge_id, scheduled_for)}
        self._authorized_purges: dict[int, tuple[int, datetime]] = {}
        # Track cancel_pending purges: {guild_id: (purge_id, expires_at)}
        self._cancel_pending_purges: dict[int, tuple[int, datetime]] = {}
        # Track messages scheduled for deletion: {(channel_id, message_id): delete_at}
        self._pending_deletions: dict[tuple[int, int], datetime] = {}
        # Cog-level settings (from env/json, not editable via web)
        self._cog_settings = get_purge_settings()
        logger.info("PurgeCog initialized")

    @staticmethod
    def get_config_schema() -> Any:
        """Get the cog configuration schema.

        Returns:
            CogConfigSchema: Configuration schema.
        """
        return PURGE_CONFIG_SCHEMA

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Get options locked by deployment configuration.

        Locked options appear disabled in the web UI.

        Returns:
            dict[str, dict[str, Any]]: Map of key -> {locked, reason}
        """
        locked: dict[str, dict[str, Any]] = {}

        if not self._cog_settings.test_mode_allowed:
            locked[ConfigKey.TEST_MODE] = {
                "locked": True,
                "reason": "Disabled by the system administrator",
            }

        return locked

    def _is_test_mode_enabled(self, config: dict[str, Any]) -> bool:
        """Check if test mode is enabled.

        Checks both the guild configuration and deployment settings.

        Args:
            config: Guild configuration.

        Returns:
            bool: True if test mode is enabled and allowed.
        """
        # If deployment doesn't allow test_mode, always return False
        if not self._cog_settings.test_mode_allowed:
            return False
        enabled: bool = config.get(ConfigKey.TEST_MODE, False)
        return enabled

    # =========================================================================
    # Config helpers
    # =========================================================================

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Check if the cog is enabled in a guild.

        Args:
            guild_id (int): Guild ID.

        Returns:
            bool: True if enabled.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Get all cog configuration for a guild.

        Args:
            guild_id (int): Guild ID.

        Returns:
            dict[str, Any]: Cog configuration.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    def _get_available_purge_types(self, config: dict[str, Any]) -> dict[str, bool]:
        """Check which purge types have complete configuration.

        Args:
            config (dict[str, Any]): Configuration dictionary.

        Returns:
            dict[str, bool]: Dictionary with available types.
        """
        result: dict[str, bool] = {"war": False, "global": False}

        # Required channels (common to all types)
        has_channels = bool(
            config.get(ConfigKey.MOD_CHANNEL) and config.get(ConfigKey.USER_CHANNEL)
        )

        if not has_channels:
            return result

        # Check war purge configuration
        if config.get(ConfigKey.WAR_ADMIN_ROLES) and config.get(ConfigKey.WAR_AFFECTED_ROLES):
            result["war"] = True

        # Check global purge configuration
        if config.get(ConfigKey.GLOBAL_ADMIN_ROLES):
            result["global"] = True

        return result

    def _get_required_reactions(self, config: dict[str, Any]) -> int:
        """Get the number of required reactions.

        In test mode, the configured value is respected.
        In normal mode, the minimum is 2.

        Args:
            config (dict[str, Any]): Cog configuration.

        Returns:
            int: Number of required reactions.
        """
        test_mode = self._is_test_mode_enabled(config)
        required: int = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
        if not test_mode and required < 2:
            required = 2
        return required

    def _get_purge_display_name(self, config: dict[str, Any], purge_type: PurgeType) -> str:
        """Get the display name for a purge type.

        Args:
            config: Cog configuration.
            purge_type: Purge type.

        Returns:
            str: Display name.
        """
        if purge_type == PurgeType.GLOBAL:
            name: str = config.get(ConfigKey.GLOBAL_DISPLAY_NAME, "Global purge")
            return name
        name = config.get(ConfigKey.WAR_DISPLAY_NAME, "War end purge")
        return name

    # =========================================================================
    # Logging helpers
    # =========================================================================

    async def _send_log(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        public_id: str,
        message: str,
        audit_level_required: int = 0,
    ) -> None:
        """Send message to log channel if configured.

        Args:
            guild: Guild where to send the log
            config: Cog configuration
            public_id: Public ID of the purge for prefix (NanoID)
            message: Message to send (already formatted)
            audit_level_required: Minimum audit level to send
        """
        # Check audit level
        current_audit = config.get(ConfigKey.AUDIT_LEVEL, 0)
        if current_audit < audit_level_required:
            return

        channel_id = config.get(ConfigKey.LOG_CHANNEL)
        if not channel_id:
            return

        try:
            channel = guild.get_channel(int(channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                log_message = f"[#{public_id}] {message}"
                await channel.send(log_message)
        except (ValueError, TypeError) as e:
            logger.warning(f"[{guild.name}] Error with purge log channel: {e}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Error sending purge log: {e}")

    # =========================================================================
    # Dynamic command registration
    # =========================================================================

    async def _register_guild_commands(self, guild: discord.Guild) -> None:
        """Register commands for a guild based on its configuration.

        Only registers commands if the cog is enabled AND essential
        configuration is complete for each type.

        Args:
            guild (discord.Guild): Discord guild.
        """
        # Check if cog is enabled
        if not await self._is_cog_enabled(guild.id):
            logger.debug(f"[{guild.name}] Purge cog disabled, not registering commands")
            # Unregister if there were commands registered
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)

        # Check which purge types are available
        available_types = self._get_available_purge_types(config)

        if not any(available_types.values()):
            logger.debug(f"[{guild.name}] No purge type configured, not registering commands")
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        # Initialize guild commands dict if not exists
        if guild.id not in self._registered_commands:
            self._registered_commands[guild.id] = {}

        # Register/update purge commands
        await self._register_purge_command(
            guild=guild,
            config=config,
            purge_type=PurgeType.WAR_END,
            available=available_types["war"],
        )
        await self._register_purge_command(
            guild=guild,
            config=config,
            purge_type=PurgeType.GLOBAL,
            available=available_types["global"],
        )

    async def _register_purge_command(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        purge_type: PurgeType,
        available: bool,
    ) -> None:
        """Register or update a purge command.

        Args:
            guild (discord.Guild): Discord guild.
            config (dict[str, Any]): Cog configuration.
            purge_type (PurgeType): Purge type (WAR_END or GLOBAL).
            available (bool): If the configuration is complete.
        """
        # Configuration per purge type
        type_config = {
            PurgeType.WAR_END: {
                "key": "war",
                "name_config": ConfigKey.WAR_COMMAND_NAME,
                "default_name": "purge_war",
                "description": "Starts a war end purge",
            },
            PurgeType.GLOBAL: {
                "key": "global",
                "name_config": ConfigKey.GLOBAL_COMMAND_NAME,
                "default_name": "purge_global",
                "description": "Starts a global purge",
            },
        }

        cfg = type_config[purge_type]
        command_key = cfg["key"]
        command_name = config.get(cfg["name_config"], cfg["default_name"])
        old_command_name = self._registered_commands.get(guild.id, {}).get(command_key)

        # If not available, remove existing command
        if not available:
            if old_command_name:
                self.bot.tree.remove_command(old_command_name, guild=guild)
                del self._registered_commands[guild.id][command_key]
                logger.info(f"[{guild.name}] Command '/{old_command_name}' removed")
            return

        # Remove old command if name changed
        if old_command_name and old_command_name != command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            logger.info(f"[{guild.name}] Command '/{old_command_name}' removed")

        # Check if command already registered with same name
        if old_command_name == command_name:
            return

        # Create and register the purge command
        @app_commands.command(
            name=command_name,
            description=cfg["description"],
        )
        @app_commands.describe(hours="Number of hours until purge execution")
        async def purge_command(
            interaction: discord.Interaction,
            hours: app_commands.Range[int, 1, 720],
            _purge_type: PurgeType = purge_type,
        ) -> None:
            await self._handle_purge(interaction=interaction, hours=hours, purge_type=_purge_type)

        # Add command to guild
        self.bot.tree.add_command(purge_command, guild=guild)
        self._registered_commands[guild.id][command_key] = command_name
        logger.info(f"[{guild.name}] Command '/{command_name}' registered")

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Remove registered commands from a guild.

        Args:
            guild (discord.Guild): Discord guild.
        """
        commands = self._registered_commands.get(guild.id, {})
        for _purge_type, command_name in list(commands.items()):
            self.bot.tree.remove_command(command_name, guild=guild)
            logger.info(f"[{guild.name}] Command '/{command_name}' removed")
        if guild.id in self._registered_commands:
            del self._registered_commands[guild.id]

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sync commands of a guild with Discord.

        Args:
            guild (discord.Guild): Discord guild.
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"[{guild.name}] Commands synced")
        except Exception as e:
            logger.error(f"[{guild.name}] Error syncing commands: {e}")

    async def _debounced_register_and_sync(self, guild: discord.Guild) -> None:
        """Register and sync commands with debounce.

        Waits a brief period before executing to batch multiple
        configuration changes into a single sync.

        Args:
            guild (discord.Guild): Discord guild.
        """
        # Cancel any pending sync for this guild
        if guild.id in self._pending_syncs:
            self._pending_syncs[guild.id].cancel()

        async def _delayed_sync() -> None:
            try:
                await asyncio.sleep(self._sync_debounce_delay)
                await self._register_guild_commands(guild)
                await self._sync_guild_commands(guild)
            except asyncio.CancelledError:
                pass  # Task was cancelled, a new one will run
            finally:
                self._pending_syncs.pop(guild.id, None)

        self._pending_syncs[guild.id] = asyncio.create_task(_delayed_sync())

    # =========================================================================
    # Command handlers
    # =========================================================================

    def _build_config_snapshot(
        self, config: dict[str, Any], purge_type: PurgeType
    ) -> dict[str, Any]:
        """Build configuration snapshot according to purge type.

        Args:
            config (dict[str, Any]): Cog configuration.
            purge_type (PurgeType): Purge type.

        Returns:
            dict[str, Any]: Configuration snapshot.
        """
        # Common fields
        snapshot: dict[str, Any] = {
            "reaction_role": config.get(ConfigKey.USER_REACTION_ROLE),
            "required_reactions": config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2),
            "test_mode": self._is_test_mode_enabled(config),
        }

        if purge_type == PurgeType.GLOBAL:
            snapshot.update(
                {
                    "excluded_roles": config.get(ConfigKey.GLOBAL_EXCLUDED_ROLES, []),
                    "roles_to_remove": config.get(ConfigKey.GLOBAL_ROLES_TO_REMOVE, []),
                    "roles_to_add": config.get(ConfigKey.GLOBAL_ROLES_TO_ADD, []),
                }
            )
        else:
            # WAR_END
            snapshot.update(
                {
                    "affected_roles": config.get(ConfigKey.WAR_AFFECTED_ROLES, []),
                    "roles_to_remove": config.get(ConfigKey.WAR_ROLES_TO_REMOVE, []),
                    "roles_to_add": config.get(ConfigKey.WAR_ROLES_TO_ADD, []),
                    "global_roles_to_remove": config.get(ConfigKey.WAR_GLOBAL_ROLES_TO_REMOVE, []),
                    "promotions": config.get(ConfigKey.WAR_PROMOTIONS, []),
                    "default_promotion": config.get(ConfigKey.WAR_DEFAULT_PROMOTION),
                }
            )

        return snapshot

    async def _handle_purge(
        self,
        interaction: discord.Interaction,
        hours: int,
        purge_type: PurgeType,
    ) -> None:
        """Handle the purge command (unified for all types).

        Args:
            interaction (discord.Interaction): Discord interaction.
            hours (int): Number of hours until execution.
            purge_type (PurgeType): Type of purge to start.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        config = await self._get_config(guild.id)

        # Check permissions according to purge type
        admin_roles = self._get_admin_roles_for_purge(config=config, purge_type=purge_type)
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.followup.send(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions."),
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            purge_service = PurgeService(session)

            # Check if there's an active purge (with lock to prevent race condition)
            active = await purge_service.get_active_purge_for_update(guild.id)
            if active:
                await interaction.followup.send(
                    config.get(
                        ConfigKey.MOD_ACTIVE_PURGE_TEXT,
                        "There's already an active purge.",
                    ),
                    ephemeral=True,
                )
                return

            # Calculate execution date (rounded to the next hour)
            now = datetime.now(UTC)
            scheduled_for = now + timedelta(hours=hours)
            # Round up to the next hour
            if scheduled_for.minute > 0 or scheduled_for.second > 0:
                scheduled_for = (scheduled_for + timedelta(hours=1)).replace(
                    minute=0, second=0, microsecond=0
                )
            else:
                scheduled_for = scheduled_for.replace(second=0, microsecond=0)

            # Calculate expiration date for authorizations
            timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
            expires_at = None
            if timeout_minutes > 0:
                expires_at = now + timedelta(minutes=timeout_minutes)

            # Create relevant config snapshot
            config_snapshot = self._build_config_snapshot(config=config, purge_type=purge_type)

            # Create purge record
            record = await purge_service.create_purge(
                guild_id=guild.id,
                purge_type=purge_type,
                initiated_by=user.id,
                config_snapshot=config_snapshot,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )

            logger.info(f"[{guild.name}] Purge {record.id} created by {user.display_name}")

            # Send creation log
            display_name = self._get_purge_display_name(config=config, purge_type=purge_type)
            log_template = config.get(
                ConfigKey.LOG_CREATED,
                "Purge **{purge_type}** created by **{user}** - "
                "Execution: {scheduled_for} ({hours}h)",
            )
            log_message = log_template.format(
                user=user.display_name,
                purge_type=display_name,
                hours=str(hours),
                scheduled_for=scheduled_for.strftime("%Y-%m-%d %H:%M UTC"),
            )
            await self._send_log(
                guild=guild,
                config=config,
                public_id=record.public_id,
                message=log_message,
            )

            # Get moderation channel
            mod_channel_id = config.get(ConfigKey.MOD_CHANNEL)
            if not mod_channel_id:
                await interaction.followup.send(
                    "Error: Moderation channel not configured.",
                    ephemeral=True,
                )
                return
            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
                await interaction.followup.send(
                    "Error: Moderation channel not found.",
                    ephemeral=True,
                )
                return

            # Calculate required authorizations
            required = self._get_required_reactions(config)

            # Check if we already have enough authorizations (initiator counts)
            authorized_count = len(record.authorized_by)
            if authorized_count >= required:
                # Auto-authorize
                updated_record = await self._authorize_purge(
                    guild=guild,
                    record=record,
                    config=config,
                    purge_service=purge_service,
                    session=session,
                )
                if updated_record:
                    record = updated_record

            # Create moderation message
            content = get_mod_message_content(guild=guild, record=record, config=config)
            view = self._create_mod_view(record=record, config=config)

            mod_message = await mod_channel.send(content=content, view=view)

            # Update record with message ID
            await purge_service.update_mod_message(
                purge_id=record.id,
                channel_id=mod_channel.id,
                message_id=mod_message.id,
            )

            # Send message to users if already authorized
            if record.status == PurgeStatus.AUTHORIZED:
                await self._send_user_message(
                    guild=guild, record=record, config=config, session=session
                )
            else:
                # Register in memory for expiration control
                self._active_purges[guild.id] = (record.id, expires_at)

            await session.commit()

            await interaction.followup.send(
                f"Purge started. Message sent to {mod_channel.mention}.",
                ephemeral=True,
            )

    # =========================================================================
    # Authorization handlers
    # =========================================================================

    def _get_admin_roles_for_purge(
        self, config: dict[str, Any], purge_type: PurgeType
    ) -> list[int]:
        """Get admin roles according to purge type.

        Args:
            config (dict[str, Any]): Cog configuration.
            purge_type (PurgeType): Purge type.

        Returns:
            list[int]: List of admin role IDs.
        """
        if purge_type == PurgeType.GLOBAL:
            roles: list[int] = config.get(ConfigKey.GLOBAL_ADMIN_ROLES, [])
            return roles
        # WAR_END and other types use WAR_ADMIN_ROLES
        roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        return roles

    async def _handle_authorize(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle purge authorization.

        Args:
            interaction (discord.Interaction): Button interaction.
            public_id (str): Public ID of the purge record (NanoID).
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer()

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purge_service = PurgeService(session)

            record = await purge_service.get_by_public_id(public_id)
            if not record or record.guild_id != guild.id:
                await interaction.followup.send(
                    "Purge not found.",
                    ephemeral=True,
                )
                return

            # Check permissions according to purge type
            admin_roles = self._get_admin_roles_for_purge(
                config=config, purge_type=PurgeType(record.purge_type)
            )
            if not has_any_role(member=user, role_ids=admin_roles):
                await interaction.followup.send(
                    config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions."),
                    ephemeral=True,
                )
                return

            if record.status not in (PurgeStatus.PENDING, PurgeStatus.AUTHORIZED):
                await interaction.followup.send(
                    "This purge is no longer active.",
                    ephemeral=True,
                )
                return

            # Add authorization (no toggle)
            if user.id in record.authorized_by:
                await interaction.followup.send(
                    "You have already authorized this purge.",
                    ephemeral=True,
                )
                return

            record = await purge_service.add_authorization(purge_id=record.id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Authorization added to purge {record.id} by {user.display_name}"
            )

            # Calculate required authorizations
            required = self._get_required_reactions(config)
            authorized_count = len(record.authorized_by)

            # Send authorization log
            log_template = config.get(
                ConfigKey.LOG_AUTHORIZED,
                "**{user}** authorized ({auth_count}/{required})",
            )
            log_message = log_template.format(
                user=user.display_name,
                auth_count=str(authorized_count),
                required=str(required),
            )
            await self._send_log(
                guild=guild,
                config=config,
                public_id=record.public_id,
                message=log_message,
            )

            if authorized_count >= required and record.status == PurgeStatus.PENDING:
                # Authorize purge
                updated_record = await self._authorize_purge(
                    guild=guild,
                    record=record,
                    config=config,
                    purge_service=purge_service,
                    session=session,
                )
                if updated_record:
                    record = updated_record

            # Update moderation message
            await self._update_mod_message(guild=guild, record=record, config=config)

            await session.commit()

            await interaction.followup.send(
                f"Authorization added. ({authorized_count}/{required})",
                ephemeral=True,
            )

    async def _handle_cancel(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle purge cancellation vote.

        Cancellation requires the same number of votes as authorization.

        Args:
            interaction (discord.Interaction): Button interaction.
            public_id (str): Public ID of the purge record (NanoID).
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer()

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purge_service = PurgeService(session)

            record = await purge_service.get_by_public_id(public_id)
            if not record or record.guild_id != guild.id:
                await interaction.followup.send(
                    "Purge not found.",
                    ephemeral=True,
                )
                return

            # Check permissions according to purge type
            admin_roles = self._get_admin_roles_for_purge(
                config=config, purge_type=PurgeType(record.purge_type)
            )
            if not has_any_role(member=user, role_ids=admin_roles):
                await interaction.followup.send(
                    config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions."),
                    ephemeral=True,
                )
                return

            if record.status not in (
                PurgeStatus.PENDING,
                PurgeStatus.AUTHORIZED,
                PurgeStatus.CANCEL_PENDING,
            ):
                await interaction.followup.send(
                    "This purge cannot be cancelled.",
                    ephemeral=True,
                )
                return

            # Check if already voted to cancel
            if user.id in record.cancelled_by:
                await interaction.followup.send(
                    "You have already voted to cancel this purge.",
                    ephemeral=True,
                )
                return

            # Add cancellation vote
            record = await purge_service.add_cancellation(purge_id=record.id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Cancellation vote added to purge {record.id} "
                f"by {user.display_name}"
            )

            # Calculate required votes
            required = self._get_required_reactions(config)
            cancel_count = len(record.cancelled_by)

            # If AUTHORIZED and first vote, transition to CANCEL_PENDING
            # (except in test mode with required=1, which goes directly to CANCELLED)
            if record.status == PurgeStatus.AUTHORIZED and cancel_count < required:
                record = await purge_service.update_status(
                    purge_id=record.id, status=PurgeStatus.CANCEL_PENDING
                )
                if not record:
                    return

                # Calculate expiration for CANCEL_PENDING
                timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
                if timeout_minutes > 0:
                    cancel_expires_at = datetime.now(UTC) + timedelta(minutes=timeout_minutes)
                    self._cancel_pending_purges[guild.id] = (record.id, cancel_expires_at)

                logger.info(f"[{guild.name}] Purge {record.id} in CANCEL_PENDING status")

            if cancel_count >= required:
                # Cancel the purge
                record = await purge_service.update_status(
                    purge_id=record.id, status=PurgeStatus.CANCELLED
                )

                if not record:
                    return

                logger.info(f"[{guild.name}] Purge {record.id} cancelled")

                # Send cancellation log
                log_template = config.get(
                    ConfigKey.LOG_CANCELLED,
                    "Cancelled by **{user}**",
                )
                log_message = log_template.format(user=user.display_name)
                await self._send_log(
                    guild=guild,
                    config=config,
                    public_id=record.public_id,
                    message=log_message,
                )

                # Remove from tracking
                self._active_purges.pop(guild.id, None)
                self._authorized_purges.pop(guild.id, None)
                self._cancel_pending_purges.pop(guild.id, None)

                # Remove reaction role from all who confirmed
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id and record.confirmed_by:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        for confirmed_user_id in record.confirmed_by:
                            member = guild.get_member(confirmed_user_id)
                            if member and role in member.roles:
                                try:
                                    await member.remove_roles(role)
                                except discord.Forbidden:
                                    logger.warning(
                                        f"Could not remove role {role.name} from {member.name}"
                                    )

                # Delete user message if exists
                if record.user_message_id and record.user_channel_id:
                    await delete_message(
                        guild=guild,
                        channel_id=record.user_channel_id,
                        message_id=record.user_message_id,
                    )

                # Update moderation message (remove buttons, show cancelled)
                await self._update_mod_message(
                    guild=guild, record=record, config=config, remove_view=True
                )

                # Schedule message deletion if retention is configured
                self._maybe_schedule_mod_message_deletion(record=record, config=config)

                await session.commit()

                await interaction.followup.send(
                    "Purge cancelled.",
                    ephemeral=True,
                )
            else:
                # Not enough votes yet
                # Update moderation message with current votes
                await self._update_mod_message(guild=guild, record=record, config=config)

                await session.commit()

                await interaction.followup.send(
                    f"Cancellation vote added. ({cancel_count}/{required})",
                    ephemeral=True,
                )

    # =========================================================================
    # User confirmation handlers
    # =========================================================================

    async def _handle_confirm(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle user stay confirmation.

        Args:
            interaction (discord.Interaction): Button interaction.
            public_id (str): Public ID of the purge record (NanoID).
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purge_service = PurgeService(session)

            record = await purge_service.get_by_public_id(public_id)
            if not record or record.guild_id != guild.id:
                await interaction.response.send_message(
                    "Purge not found.",
                    ephemeral=True,
                )
                return

            if record.status != PurgeStatus.AUTHORIZED:
                await interaction.response.send_message(
                    "This purge is no longer active.",
                    ephemeral=True,
                )
                return

            # Toggle confirmation
            was_confirmed = user.id in record.confirmed_by
            if was_confirmed:
                record = await purge_service.remove_confirmation(
                    purge_id=record.id, user_id=user.id
                )
                message = config.get(
                    ConfigKey.USER_REMOVED_REACTION_TEXT,
                    "You have withdrawn your confirmation.",
                )
                # Remove role if configured
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.remove_roles(role)
                        except discord.Forbidden:
                            logger.warning(
                                f"[{guild.name}] Could not remove role "
                                f"@{role.name} from {user.name}"
                            )
            else:
                record = await purge_service.add_confirmation(purge_id=record.id, user_id=user.id)
                message = config.get(
                    ConfigKey.USER_FIRST_REACTION_TEXT,
                    "You have confirmed your stay.",
                )
                # Assign role if configured
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.add_roles(role)
                        except discord.Forbidden:
                            logger.warning(
                                f"[{guild.name}] Could not assign role @{role.name} to {user.name}"
                            )

            await session.commit()

            await interaction.response.send_message(message, ephemeral=True)

    # =========================================================================
    # Message update helpers
    # =========================================================================

    def _create_mod_view(
        self,
        record: PurgeRecord,
        config: dict[str, Any],
    ) -> ModAuthorizationView:
        """Create moderation view with buttons according to status.

        Args:
            record (PurgeRecord): Purge record.
            config (dict[str, Any]): Cog configuration.

        Returns:
            ModAuthorizationView: View with appropriate buttons.
        """
        button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
        authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Authorize purge")
        cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Stop purge")

        return ModAuthorizationView(
            public_id=record.public_id,
            status=PurgeStatus(record.status),
            authorize_label=authorize_label,
            cancel_label=cancel_label,
            button_style=get_button_style(button_color),
        )

    def _maybe_schedule_mod_message_deletion(
        self,
        record: PurgeRecord,
        config: dict[str, Any],
    ) -> None:
        """Schedule moderation message deletion if retention is configured.

        Args:
            record (PurgeRecord): Purge record.
            config (dict[str, Any]): Cog configuration.
        """
        retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
        if retention > 0 and record.mod_channel_id and record.mod_message_id:
            self._schedule_message_deletion(
                channel_id=record.mod_channel_id,
                message_id=record.mod_message_id,
                retention_minutes=retention,
            )

    async def _authorize_purge(
        self,
        guild: discord.Guild,
        record: PurgeRecord,
        config: dict[str, Any],
        purge_service: PurgeService,
        session: Any,
    ) -> PurgeRecord | None:
        """Transition a purge to AUTHORIZED status.

        Args:
            guild (discord.Guild): Discord guild.
            record (PurgeRecord): Purge record.
            config (dict[str, Any]): Cog configuration.
            purge_service (PurgeService): Purge service.
            session (AsyncSession): Database session.

        Returns:
            PurgeRecord | None: Updated record or None if failed.
        """
        test_mode = self._is_test_mode_enabled(config)

        # Calculate execution time
        exec_scheduled_for: datetime | None
        if test_mode:
            exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
        else:
            exec_scheduled_for = record.scheduled_for

        # Update status
        updated_record = await purge_service.update_status(
            purge_id=record.id,
            status=PurgeStatus.AUTHORIZED,
            scheduled_for=exec_scheduled_for,
        )

        if not updated_record:
            return None

        logger.info(
            f"[{guild.name}] Purge {record.id} authorized, "
            f"execution scheduled for {exec_scheduled_for}"
        )

        # Remove from expiration tracking
        self._active_purges.pop(guild.id, None)

        # Add to execution tracking
        if exec_scheduled_for:
            self._authorized_purges[guild.id] = (updated_record.id, exec_scheduled_for)

        # Send message to user channel
        await self._send_user_message(
            guild=guild, record=updated_record, config=config, session=session
        )

        return updated_record

    async def _update_mod_message(
        self,
        guild: discord.Guild,
        record: PurgeRecord,
        config: dict[str, Any],
        remove_view: bool = False,
        execution_logs: list[str] | None = None,
    ) -> None:
        """Update the moderation message.

        Args:
            guild (discord.Guild): Guild.
            record (PurgeRecord): Purge record.
            config (dict[str, Any]): Configuration.
            remove_view (bool): If True, removes the buttons.
            execution_logs (list[str] | None): Execution logs to add.
        """
        if not record.mod_message_id or not record.mod_channel_id:
            return

        channel = guild.get_channel(record.mod_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(record.mod_message_id)
        except discord.NotFound:
            logger.warning(f"[{guild.name}] Purge moderation message not found")
            return

        content = get_mod_message_content(
            guild=guild, record=record, config=config, execution_logs=execution_logs
        )

        if remove_view or record.status in (
            PurgeStatus.CANCELLED,
            PurgeStatus.EXPIRED,
            PurgeStatus.EXECUTED,
            PurgeStatus.FAILED,
        ):
            await message.edit(content=content, view=None)
        elif record.status in (
            PurgeStatus.PENDING,
            PurgeStatus.AUTHORIZED,
            PurgeStatus.CANCEL_PENDING,
        ):
            view = self._create_mod_view(record=record, config=config)
            await message.edit(content=content, view=view)
        else:
            await message.edit(content=content)

    async def _send_user_message(
        self,
        guild: discord.Guild,
        record: PurgeRecord,
        config: dict[str, Any],
        session: Any,
    ) -> None:
        """Send message to user channel.

        Args:
            guild (discord.Guild): Guild.
            record (PurgeRecord): Purge record.
            config (dict[str, Any]): Configuration.
            session (AsyncSession): Database session.
        """
        user_channel_id = config.get(ConfigKey.USER_CHANNEL)
        if not user_channel_id:
            return

        channel = guild.get_channel(user_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Get template and roles according to purge type
        purge_type = PurgeType(record.purge_type)
        if purge_type == PurgeType.GLOBAL:
            template = config.get(ConfigKey.GLOBAL_MESSAGE_TEMPLATE)
            excluded_roles = config.get(ConfigKey.GLOBAL_EXCLUDED_ROLES, [])
            roles_text = format_roles(guild=guild, role_ids=excluded_roles)
        else:
            template = config.get(ConfigKey.WAR_MESSAGE_TEMPLATE)
            affected_roles = config.get(ConfigKey.WAR_AFFECTED_ROLES, [])
            roles_text = format_roles(guild=guild, role_ids=affected_roles)

        reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
        reaction_role = guild.get_role(reaction_role_id) if reaction_role_id else None
        reaction_role_text = reaction_role.mention if reaction_role else ""

        # Calculate date with Discord format (dynamic timestamp)
        scheduled_date = "Not scheduled"
        scheduled_time = ""
        discord_timestamp = ""
        discord_timestamp_relative = ""
        if record.scheduled_for:
            unix_ts = int(record.scheduled_for.timestamp())
            scheduled_date = record.scheduled_for.strftime("%Y-%m-%d")
            scheduled_time = record.scheduled_for.strftime("%H:%M UTC")
            # Discord format: full date + relative
            discord_timestamp = f"<t:{unix_ts}:f>"
            discord_timestamp_relative = f"<t:{unix_ts}:R>"

        content = format_message(
            template=template,
            roles=roles_text,
            fecha=f"{discord_timestamp} ({discord_timestamp_relative})",
            fecha_relativa=discord_timestamp_relative,
            reaction_role=reaction_role_text,
            # Maintain compatibility with old placeholders
            dia=f"{scheduled_date} {scheduled_time}",
            reaction_rol=reaction_role_text,
        )

        # Create view with button
        button_color = config.get(ConfigKey.USER_BUTTON_COLOR, "green")
        confirm_label = config.get(ConfigKey.USER_BUTTON_TEXT, "🛡️ Confirm stay")

        view = UserConfirmationView(
            public_id=record.public_id,
            confirm_label=confirm_label,
            button_style=get_button_style(button_color),
        )

        user_message = await channel.send(content=content, view=view)

        # Update record
        purge_service = PurgeService(session)
        await purge_service.update_user_message(
            purge_id=record.id,
            channel_id=channel.id,
            message_id=user_message.id,
        )

    # =========================================================================
    # Event listeners
    # =========================================================================

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Register commands when the bot is ready."""
        logger.info("PurgeCog: Registering commands in all guilds...")
        for guild in self.bot.guilds:
            try:
                await self._register_guild_commands(guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Error registering commands: {e}")

        # Sync commands for all guilds
        for guild in self.bot.guilds:
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)

        logger.info("PurgeCog: Command registration completed")

        # Restore active purges from database
        await self._restore_active_purges()

        # Check expiration immediately
        await self._check_expired_purges()

        # Start expiration check task
        if not self.expiration_check_loop.is_running():
            self.expiration_check_loop.start()

    async def _restore_active_purges(self) -> None:
        """Restore pending and authorized purges from database on startup.

        This allows active purges to continue being monitored
        after a bot restart.
        """
        try:
            async with self.bot.database.session() as session:
                purge_service = PurgeService(session)

                # Restore pending authorization purges
                pending_purges = await purge_service.get_pending_purges()
                for record in pending_purges:
                    self._active_purges[record.guild_id] = (record.id, record.expires_at)
                    logger.info(f"Pending purge {record.id} restored for guild {record.guild_id}")

                # Restore authorized purges pending execution
                authorized_purges = await purge_service.get_authorized_purges()
                for record in authorized_purges:
                    if record.scheduled_for:
                        self._authorized_purges[record.guild_id] = (record.id, record.scheduled_for)
                        logger.info(
                            f"Authorized purge {record.id} restored for guild {record.guild_id}"
                        )

                # Restore purges with pending cancellation
                cancel_pending_purges = await purge_service.get_cancel_pending_purges()
                for record in cancel_pending_purges:
                    # Use fresh timeout from config when restoring
                    config = await self._get_config(record.guild_id)
                    timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
                    if timeout_minutes > 0:
                        cancel_expires_at = datetime.now(UTC) + timedelta(minutes=timeout_minutes)
                        self._cancel_pending_purges[record.guild_id] = (
                            record.id,
                            cancel_expires_at,
                        )
                        logger.info(
                            f"CANCEL_PENDING purge {record.id} restored for guild {record.guild_id}"
                        )

                total = len(pending_purges) + len(authorized_purges) + len(cancel_pending_purges)
                if total:
                    logger.info(f"PurgeCog: {total} purges restored")
        except Exception as e:
            logger.error(f"Error restoring active purges: {e}")

    async def cog_unload(self) -> None:
        """Clean up resources when unloading the cog."""
        self.expiration_check_loop.cancel()

    def _schedule_message_deletion(
        self, channel_id: int, message_id: int, retention_minutes: int
    ) -> None:
        """Schedule message deletion.

        Args:
            channel_id (int): Channel ID.
            message_id (int): Message ID.
            retention_minutes (int): Minutes until deletion. 0 = don't delete.
        """
        if retention_minutes > 0:
            delete_at = datetime.now(UTC) + timedelta(minutes=retention_minutes)
            self._pending_deletions[(channel_id, message_id)] = delete_at
            logger.debug(f"Mod message (ID: {message_id}) scheduled for deletion: {delete_at}")

    async def _check_pending_deletions(self) -> None:
        """Check and delete messages that have passed their retention time."""
        now = datetime.now(UTC)
        to_delete: list[tuple[int, int]] = []

        for (channel_id, message_id), delete_at in self._pending_deletions.items():
            if delete_at <= now:
                to_delete.append((channel_id, message_id))

        for channel_id, message_id in to_delete:
            self._pending_deletions.pop((channel_id, message_id), None)
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                continue

            guild = channel.guild
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
                logger.info(
                    f"[{guild.name}] Moderation message deleted due to retention in #{channel.name}"
                )
            except discord.NotFound:
                pass  # Already deleted
            except Exception as e:
                logger.error(
                    f"[{guild.name}] Error deleting moderation message (ID: {message_id}): {e}"
                )

    async def _check_expired_purges(self) -> None:
        """Check and expire pending purges that have passed their time limit."""
        now = datetime.now(UTC)
        expired_guilds: list[int] = []

        # Identify expired purges
        for guild_id, (_purge_id, expires_at) in self._active_purges.items():
            if expires_at:
                # SQLite doesn't support native timezone, normalize to UTC if naive
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at <= now:
                    expired_guilds.append(guild_id)

        # Process expired purges
        for guild_id in expired_guilds:
            purge_id, _ = self._active_purges.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purge {purge_id} has expired")

            try:
                async with self.bot.database.session() as session:
                    purge_service = PurgeService(session)

                    # Update status to expired
                    record = await purge_service.update_status(
                        purge_id=purge_id, status=PurgeStatus.EXPIRED
                    )

                    if record and guild:
                        config = await self._get_config(guild_id)
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                            remove_view=True,
                        )
                        # Schedule deletion if retention is configured
                        self._maybe_schedule_mod_message_deletion(record=record, config=config)

                    await session.commit()
            except Exception as e:
                logger.error(f"[{guild_name}] Error expiring purge {purge_id}: {e}")

    async def _check_cancel_pending_expired(self) -> None:
        """Check and revert CANCEL_PENDING purges that have expired to AUTHORIZED."""
        now = datetime.now(UTC)
        expired_guilds: list[int] = []

        # Identify expired CANCEL_PENDING purges
        for guild_id, (_purge_id, expires_at) in self._cancel_pending_purges.items():
            if expires_at <= now:
                expired_guilds.append(guild_id)

        # Process expired purges
        for guild_id in expired_guilds:
            purge_id, _ = self._cancel_pending_purges.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(
                f"[{guild_name}] Purge {purge_id} cancellation expired, reverting to AUTHORIZED"
            )

            try:
                async with self.bot.database.session() as session:
                    purge_service = PurgeService(session)

                    # Clear cancellation votes
                    await purge_service.clear_cancellations(purge_id)

                    # Revert status to AUTHORIZED
                    record = await purge_service.update_status(
                        purge_id=purge_id, status=PurgeStatus.AUTHORIZED
                    )

                    if record and guild:
                        config = await self._get_config(guild_id)
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                        )

                    await session.commit()
            except Exception as e:
                logger.error(f"[{guild_name}] Error reverting purge {purge_id} cancellation: {e}")

    async def _check_ready_purges(self) -> None:
        """Check and execute authorized purges that have reached their execution time."""
        now = datetime.now(UTC)
        ready_guilds: list[int] = []

        # Identify purges ready to execute
        for guild_id, (_purge_id, scheduled_for) in self._authorized_purges.items():
            # SQLite doesn't support native timezone, normalize to UTC if naive
            if scheduled_for.tzinfo is None:
                scheduled_for = scheduled_for.replace(tzinfo=UTC)
            if scheduled_for <= now:
                ready_guilds.append(guild_id)

        # Process ready purges
        for guild_id in ready_guilds:
            purge_id, _ = self._authorized_purges.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purge {purge_id} ready to execute")

            try:
                await self._execute_purge(guild_id=guild_id, purge_id=purge_id)
            except Exception as e:
                logger.error(f"[{guild_name}] Error executing purge {purge_id}: {e}")

    async def _execute_purge(self, guild_id: int, purge_id: int) -> None:
        """Execute a purge.

        Args:
            guild_id (int): Guild ID.
            purge_id (int): Purge ID.
        """
        await execute_purge(cog=self, guild_id=guild_id, purge_id=purge_id)

    @tasks.loop(minutes=1)
    async def expiration_check_loop(self) -> None:
        """Loop that checks expired purges, executions and pending messages."""
        await self._check_expired_purges()
        await self._check_cancel_pending_expired()
        await self._check_ready_purges()
        await self._check_pending_deletions()

    @expiration_check_loop.before_loop
    async def before_expiration_check(self) -> None:
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Register commands when the bot joins a guild.

        Args:
            guild (discord.Guild): Guild the bot joined.
        """
        logger.info(f"[{guild.name}] PurgeCog: Bot joined, registering commands...")
        await self._register_guild_commands(guild)
        if guild.id in self._registered_commands:
            await self._sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle button interactions with dynamic IDs.

        Buttons have custom_ids like 'purge:authorize:123' that include
        the purge_id. This listener handles these buttons so they work
        even after restarting the bot.

        Args:
            interaction (discord.Interaction): Received interaction.
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id: str = str(interaction.data.get("custom_id", "") if interaction.data else "")

        # Handle authorize button: purge:authorize:{public_id}
        if custom_id.startswith("purge:authorize:"):
            public_id = custom_id.split(":")[2]
            await self._handle_authorize(interaction=interaction, public_id=public_id)
            return

        # Handle cancel button: purge:cancel:{public_id}
        if custom_id.startswith("purge:cancel:"):
            public_id = custom_id.split(":")[2]
            await self._handle_cancel(interaction=interaction, public_id=public_id)
            return

        # Handle confirm button: purge:confirm:{public_id}
        if custom_id.startswith("purge:confirm:"):
            public_id = custom_id.split(":")[2]
            await self._handle_confirm(interaction=interaction, public_id=public_id)
            return

    # =========================================================================
    # Config change callbacks
    # =========================================================================

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Callback when the cog is enabled or disabled.

        Args:
            guild (discord.Guild): Guild where the state changed.
            enabled (bool): True if enabled.
        """
        if enabled:
            logger.info(f"[{guild.name}] PurgeCog enabled, registering commands...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"[{guild.name}] PurgeCog disabled, removing commands...")
            await self._unregister_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Callback when cog configuration changes.

        Args:
            guild (discord.Guild): Guild where configuration changed.
            keys (list[str]): List of configuration keys that changed.
        """
        # Keys that affect command registration
        essential_keys = {
            # Common keys
            ConfigKey.MOD_CHANNEL,
            ConfigKey.USER_CHANNEL,
            # War purge keys
            ConfigKey.WAR_COMMAND_NAME,
            ConfigKey.WAR_ADMIN_ROLES,
            ConfigKey.WAR_AFFECTED_ROLES,
            # Global purge keys
            ConfigKey.GLOBAL_COMMAND_NAME,
            ConfigKey.GLOBAL_ADMIN_ROLES,
        }

        if set(keys) & essential_keys:
            changed = set(keys) & essential_keys
            logger.debug(
                f"Essential configuration {changed} changed in {guild.name}, "
                "scheduling command re-evaluation..."
            )
            # Use debounced sync to batch multiple config changes
            await self._debounced_register_and_sync(guild)


async def setup(bot: DiscordBot) -> None:
    """Set up the cog.

    Args:
        bot (DiscordBot): Discord bot instance.
    """
    get_config_schema_service().register_schema(PURGE_CONFIG_SCHEMA)
    await bot.add_cog(PurgeCog(bot))
    logger.info("PurgeCog loaded")


async def teardown(bot: DiscordBot) -> None:
    """Clean up the cog.

    Args:
        bot (DiscordBot): Discord bot instance.
    """
    cog = bot.get_cog("PurgeCog")
    if cog and isinstance(cog, PurgeCog):
        # Unregister all commands
        for guild_id in list(cog._registered_commands.keys()):
            guild = bot.get_guild(guild_id)
            if guild:
                await cog._unregister_guild_commands(guild)
    get_config_schema_service().unregister_schema(COG_NAME)
    logger.info("PurgeCog unloaded")
