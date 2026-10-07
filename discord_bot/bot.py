"""Main Discord bot class."""

import asyncio
import logging
import time

import discord
from alembic import command
from alembic.config import Config as AlembicConfig
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from discord_bot.common.core import AppSettings
from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.enums.event_type import EventType
from discord_bot.common.models import Guild as GuildModel
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services import DatabaseService
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.event_bus import get_event_bus
from discord_bot.health import HealthChecker

logger = logging.getLogger(__name__)

# Seconds between two command recoveries of the same guild: a stale command
# raises one CommandNotFound per keystroke, so the first one starts the
# recovery and the rest ride on it.
COMMAND_RECOVERY_COOLDOWN = 300.0

# Bot configuration schema (admin permissions)
BOT_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="bot",
    display_name="Bot",
    description="General bot settings and admin permissions",
    icon="🤖",
    toggleable=False,
    options=[
        ConfigOption(
            key="admin_roles",
            name="Admin roles",
            description=(
                "Roles that can configure the bot from the web panel. "
                "The user who invited the bot and the server owner always have access."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
        ),
    ],
)


class DiscordBot(commands.Bot):
    """Main Discord bot class."""

    def __init__(self, settings: AppSettings, database: DatabaseService) -> None:
        """Initialize the Discord bot.

        Args:
            settings (AppSettings): Application settings
            database (DatabaseService): Database service
        """
        self.settings = settings
        self.database = database
        self.event_bus = get_event_bus()
        self._monitor_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        # on_ready fires again on every gateway re-IDENTIFY, so startup-only
        # work (rate-limited command sync, BOT_READY event) is done just once
        self._startup_synced = False
        # Last command recovery per guild (monotonic time) and the tasks running
        self._command_recovery_at: dict[int, float] = {}
        self._command_recovery_tasks: set[asyncio.Task[None]] = set()

        # Configure intents
        # Note: message_content and members are privileged intents that must be
        # enabled in the Discord Developer Portal
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.members = True  # Required for member information
        intents.emojis_and_stickers = True  # Required for custom emoji access

        # Initialize bot
        # max_messages=None disables the internal message cache: the bot only
        # consumes raw events and on_message, so the cache is never read
        # allowed_mentions disables everyone/role pings by default so
        # user-controlled text (nicknames, in-game names) echoed back in
        # message content cannot mass-ping; sends whose role pings are the
        # feature opt back in with a per-message AllowedMentions
        super().__init__(
            command_prefix=settings.bot.command_prefix,
            description=settings.bot.description,
            intents=intents,
            owner_id=settings.bot.owner_id,
            max_messages=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=True
            ),
        )

    async def setup_hook(self) -> None:
        """Setup hook initialization.

        Hook called during bot initialization to load extensions and set up
        the database.
        """
        logger.info("Running setup hook...")

        # Register bot configuration schema
        get_config_schema_service().register_schema(BOT_CONFIG_SCHEMA)

        # Initialize database
        await self.database.initialize()

        # Create tables
        await self._create_tables()

        # Load cogs
        await self._load_cogs()

        # Set up error handler for app commands
        self.tree.on_error = self._on_app_command_error  # type: ignore[method-assign]

        # Start event loop monitoring
        self._monitor_task = asyncio.create_task(self._monitor_event_loop())

        # Periodic self-check, process-wide; the operator sets the cadence in
        # the config (health.interval_minutes), 0 keeps it off
        if self.settings.health.enabled:
            self._health_task = asyncio.create_task(HealthChecker(bot=self).run())

        logger.info("Setup hook completed")

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle errors in application commands.

        Args:
            interaction: The interaction that caused the error.
            error: The error that was raised.
        """
        if isinstance(error, app_commands.CommandNotFound):
            # Discord still offers a command the tree no longer holds: an
            # extension reload strips the module's commands, a registration
            # failed... Answer the interaction, then ask the cogs to put the
            # guild's commands back.
            logger.warning(
                f"CommandNotFound: /{error.name} (guild: {interaction.guild}). "
                "Discord has a stale cached command."
            )
            await self._acknowledge_stale_command(interaction)
            self._schedule_command_recovery(interaction.guild)
            return

        # Log other errors and tell the user, so the interaction does not
        # end in Discord's generic "The application did not respond"
        cmd_name = interaction.command.name if interaction.command else "unknown"
        logger.error(f"App command error in /{cmd_name}: {error}", exc_info=error)
        await self._reply_command_error(interaction)

    async def _acknowledge_stale_command(self, interaction: discord.Interaction) -> None:
        """Answer an interaction for a command the tree does not hold.

        An autocomplete interaction cannot take a message: replying with an
        empty choice list keeps Discord from showing its generic loading error
        while the recovery runs.

        Args:
            interaction: The interaction Discord sent for the stale command.
        """
        try:
            if interaction.response.is_done():
                return
            if interaction.type is discord.InteractionType.autocomplete:
                await interaction.response.autocomplete([])
            else:
                await interaction.response.send_message(
                    "This command is being restored. Please try again in a few seconds.",
                    ephemeral=True,
                )
        except discord.HTTPException:
            pass  # Interaction may have expired

    def _schedule_command_recovery(self, guild: discord.Guild | None) -> None:
        """Start a background recovery of a guild's commands, at most once per cooldown.

        Args:
            guild: Guild whose commands went stale; None for interactions outside a guild.
        """
        if guild is None:
            return
        now = time.monotonic()
        last = self._command_recovery_at.get(guild.id)
        if last is not None and now - last < COMMAND_RECOVERY_COOLDOWN:
            return
        self._command_recovery_at[guild.id] = now
        task = asyncio.create_task(self._recover_guild_commands(guild))
        self._command_recovery_tasks.add(task)
        task.add_done_callback(self._command_recovery_tasks.discard)

    async def _recover_guild_commands(self, guild: discord.Guild) -> None:
        """Ask every cog that registers commands dynamically to restore the guild's.

        Cogs opt in by implementing ``recover_guild_commands(guild=...)``; one
        cog failing does not stop the others.

        Args:
            guild: Guild whose commands are being restored.
        """
        logger.info(f"[{guild.name}] Restoring commands Discord still offers but the bot lost")
        for cog in list(self.cogs.values()):
            recover = getattr(cog, "recover_guild_commands", None)
            if recover is None:
                continue
            try:
                await recover(guild=guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Error restoring {cog.qualified_name} commands: {e}")

    async def _reply_command_error(self, interaction: discord.Interaction) -> None:
        """Send a generic ephemeral failure message for an unhandled command error.

        Uses the initial response when still available and a followup when the
        command already deferred or responded.

        Args:
            interaction: The interaction whose command failed.
        """
        message = "Something went wrong while running this command. Please try again later."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass  # Interaction expired or already acknowledged elsewhere

    async def _create_tables(self) -> None:
        """Apply Alembic migrations to the database."""
        # Configure Alembic
        alembic_cfg = AlembicConfig("alembic.ini")

        # Run migrations in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")

        logger.info("Database migrations applied")

    async def _load_cogs(self) -> None:
        """Load every cog left enabled in the ``cogs`` config block.

        A disabled cog never enters the process: its commands, listeners and
        dashboard section (registered by the extension's ``setup``) all stay out.
        """
        for name in self.settings.cogs.disabled_cogs():
            logger.info(f"Cog disabled by config, not loading: {name}")

        for cog in self.settings.cogs.enabled_extensions():
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Error loading cog {cog}: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """Event handler when the bot is ready."""
        if self.user:
            logger.info(f"Bot connected as {self.user.name} (ID: {self.user.id})")
            logger.info(f"Connected to {len(self.guilds)} server(s)")
            for guild in self.guilds:
                logger.info(f"  - {guild.name} (ID: {guild.id})")

            # Reconciling runs on every ready: a re-IDENTIFY delivers guilds
            # joined during the disconnect without firing on_guild_join
            await self._reconcile_guilds()

            if self._startup_synced:
                return
            self._startup_synced = True

            # Sync application commands with Discord: this global sync is
            # heavily rate limited, so it must not repeat on reconnects
            try:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} application commands")
            except Exception as e:
                logger.error(f"Error syncing commands: {e}")

            # Emit event
            self.event_bus.emit(
                EventType.BOT_READY,
                {
                    "bot_name": self.user.name,
                    "bot_id": self.user.id,
                    "guild_count": len(self.guilds),
                },
            )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Event handler when the bot joins a server.

        Registers the server in the database and saves who invited the bot.
        """
        logger.info(f"Bot joined server: {guild.name} (ID: {guild.id})")
        invited_by_id = await self._find_inviter(guild)
        await self._save_guild(guild, invited_by_id)

    async def _find_inviter(self, guild: discord.Guild) -> int | None:
        """Find who invited the bot to a guild.

        Looks the bot up in the audit log and falls back to the server owner
        when the log is unavailable or has no matching entry.

        Args:
            guild (discord.Guild): The Discord server

        Returns:
            int | None: User ID of the inviter (or owner), None if the guild has no owner.
        """
        invited_by_id: int | None = None
        try:
            if guild.me and guild.me.guild_permissions.view_audit_log and self.user:
                async for entry in guild.audit_logs(
                    limit=10, action=discord.AuditLogAction.bot_add
                ):
                    # Find the entry corresponding to this bot
                    if entry.target and entry.user and entry.target.id == self.user.id:
                        invited_by_id = entry.user.id
                        logger.info(f"Bot invited by: {entry.user.name} (ID: {invited_by_id})")
                        break
        except discord.Forbidden:
            logger.warning(
                f"Could not access audit log for {guild.name} to determine who invited the bot"
            )
        except Exception as e:
            logger.error(f"Error querying audit log: {e}")

        # If we couldn't get the inviter, use the server owner
        if invited_by_id is None:
            invited_by_id = guild.owner_id
            logger.info(f"Using server owner as inviter: {invited_by_id}")
        return invited_by_id

    async def _reconcile_guilds(self) -> None:
        """Make sure every guild the bot is in has a current row in the database.

        on_guild_join only fires while the bot is online, so a guild that
        invited the bot during downtime would otherwise never get a row (and
        its inviter no dashboard access), and renamed guilds would keep the
        old name.
        """
        try:
            async with self.database.session() as session:
                result = await session.execute(select(GuildModel.id, GuildModel.name))
                known_names = {guild_id: name for guild_id, name in result.all()}
        except Exception as e:
            logger.error(f"Error loading guilds from the database: {e}")
            return

        for guild in self.guilds:
            try:
                if guild.id not in known_names:
                    logger.info(f"[{guild.name}] Guild missing from the database, registering it")
                    await self._save_guild(guild, await self._find_inviter(guild))
                elif known_names[guild.id] != guild.name:
                    await self._save_guild(guild, None)
            except Exception as e:
                logger.error(f"[{guild.name}] Error updating guild in the database: {e}")

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Event handler when the bot is removed from a server."""
        logger.info(f"Bot removed from server: {guild.name} (ID: {guild.id})")
        logger.info(f"Now connected to {len(self.guilds)} server(s)")

    async def _save_guild(self, guild: discord.Guild, invited_by_id: int | None) -> None:
        """Save or update a server in the database.

        Args:
            guild (discord.Guild): The Discord server
            invited_by_id (int | None): ID of the user who invited the bot
        """
        async with self.database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == guild.id))
            db_guild = result.scalar_one_or_none()

            if db_guild:
                db_guild.name = guild.name
                # Update invited_by_id when the bot is re-invited
                if invited_by_id:
                    db_guild.invited_by_id = invited_by_id
            else:
                db_guild = GuildModel(
                    id=guild.id,
                    name=guild.name,
                    invited_by_id=invited_by_id,
                )
                session.add(db_guild)

            await session.commit()
            logger.info(f"Server saved to DB: {guild.name}")

    async def _monitor_event_loop(self) -> None:
        """Monitor the event loop for blocking operations.

        This task runs continuously and checks for delays in the event loop
        that may indicate blocking operations. Logs warnings when a significant
        delay is detected.
        """
        logger.info("Event loop monitoring started")
        last_check = time.perf_counter()
        check_interval = 0.1  # Check every 100ms
        warning_threshold = self.settings.bot.event_loop_warning_threshold

        try:
            while True:
                await asyncio.sleep(check_interval)
                now = time.perf_counter()
                actual_delay = now - last_check
                expected_delay = check_interval
                lag = actual_delay - expected_delay

                if lag > warning_threshold:
                    logger.warning(
                        f"Event loop lag detected: {lag:.2f}s "
                        f"(expected {expected_delay:.2f}s, actual {actual_delay:.2f}s). "
                        "This may indicate a blocking operation in a cog!"
                    )

                last_check = now
        except asyncio.CancelledError:
            logger.info("Event loop monitoring stopped")
            raise

    async def close(self) -> None:
        """Clean shutdown of the bot."""
        logger.info("Shutting down the bot...")

        # Stop the background tasks (event loop monitor, health check)
        for task in (self._monitor_task, self._health_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Emit shutdown event
        self.event_bus.emit(EventType.BOT_SHUTDOWN, {})

        # Close database
        await self.database.close()

        # Close bot connection
        await super().close()

        logger.info("Bot shutdown completed")
