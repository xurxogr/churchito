"""Main Discord bot class."""

import asyncio
import logging
import time

import discord
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

logger = logging.getLogger(__name__)

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

        # Configure intents
        # Note: message_content and members are privileged intents that must be
        # enabled in the Discord Developer Portal
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.members = True  # Required for member information

        # Initialize bot
        super().__init__(
            command_prefix=settings.bot.command_prefix,
            description=settings.bot.description,
            intents=intents,
            owner_id=settings.bot.owner_id,
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

        # Start event loop monitoring
        self._monitor_task = asyncio.create_task(self._monitor_event_loop())

        logger.info("Setup hook completed")

    async def _create_tables(self) -> None:
        """Apply Alembic migrations to the database."""
        from alembic import command
        from alembic.config import Config

        # Configure Alembic
        alembic_cfg = Config("alembic.ini")

        # Run migrations in a thread to avoid blocking the event loop
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")

        logger.info("Database migrations applied")

    async def _load_cogs(self) -> None:
        """Load all cogs."""
        cogs_to_load = [
            "discord_bot.verification.cog",
            "discord_bot.autoname.cog",
            "discord_bot.purge.cog",
        ]

        for cog in cogs_to_load:
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

            # Sync application commands with Discord
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

        # Try to get who invited the bot from the audit log
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

        # Save to database
        await self._save_guild(guild, invited_by_id)

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

        # Stop event loop monitoring
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Emit shutdown event
        self.event_bus.emit(EventType.BOT_SHUTDOWN, {})

        # Close database
        await self.database.close()

        # Close bot connection
        await super().close()

        logger.info("Bot shutdown completed")
