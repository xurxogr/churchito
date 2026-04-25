"""User verification cog."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message
from discord_bot.verification.config import COG_NAME, VERIFICATION_CONFIG_SCHEMA
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.formatters import (
    build_mod_embed_sections,
    create_mod_embeds,
    create_panel_embed,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers import (
    get_ready_for_approval_status,
    handle_accept,
    handle_dm_screenshots,
    handle_reject,
    handle_review,
    handle_verification_start,
    show_rejection_select,
    update_mod_message_cancelled,
    update_mod_message_status,
    update_tracker_message,
)
from discord_bot.verification.panel import check_verification_message, get_mod_channel
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import ModReviewView, VerificationPanelView

logger = logging.getLogger(__name__)


class VerificationCog(commands.Cog):
    """Cog for the user verification system."""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the verification cog.

        Args:
            bot (DiscordBot): Bot instance
        """
        self.bot = bot
        self._pending_dm_verifications: dict[int, tuple[int, int]] = {}
        self._last_health_check: dict[int, datetime] = {}
        self._health_check_started = False
        # Timers for screenshot timeout: request_id -> Task
        self._screenshot_timers: dict[int, asyncio.Task[None]] = {}
        # User locks to prevent race conditions on verification start
        self._user_locks: dict[int, asyncio.Lock] = {}

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Get options locked by deployment configuration.

        Returns:
            dict[str, dict[str, Any]]: Map of key -> {locked, reason}
        """
        return {}

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a user to prevent race conditions.

        Args:
            user_id: Discord user ID

        Returns:
            asyncio.Lock: Lock for this user
        """
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def cog_load(self) -> None:
        """Register persistent views and restore state when loading the cog."""
        self.bot.add_view(VerificationPanelView())

        # Restore pending verifications from the database
        await self._restore_pending_verifications()

        # Health check starts after the bot is ready
        if not self._health_check_started:
            self.health_check_loop.start()
            self._health_check_started = True

    async def _restore_pending_verifications(self) -> None:
        """Restore pending verifications from the database."""
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            config_service = ConfigService(session=session)
            pending_requests = await service.get_all_pending_screenshots()

            now = datetime.now(UTC)
            timers_restored = 0

            for request in pending_requests:
                self._pending_dm_verifications[request.user_id] = (
                    request.guild_id,
                    request.id,
                )

                # Restore timer if configured
                config = await config_service.get_all_config(
                    guild_id=request.guild_id,
                    cog_name=COG_NAME,
                )
                timeout_minutes = config.get(ConfigKey.SCREENSHOT_TIMEOUT_MINUTES) or 0

                if timeout_minutes <= 0:
                    continue

                # Calculate remaining time
                created_at = request.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                elapsed_minutes = (now - created_at).total_seconds() / 60
                remaining_minutes = timeout_minutes - elapsed_minutes

                if remaining_minutes <= 0:
                    # Time already passed, reject immediately
                    asyncio.create_task(
                        self._auto_reject_by_timeout(
                            request_id=request.id,
                            guild_id=request.guild_id,
                            user_id=request.user_id,
                        )
                    )
                    continue

                # Still time left, restore timer
                self.start_screenshot_timer(
                    request_id=request.id,
                    guild_id=request.guild_id,
                    user_id=request.user_id,
                    timeout_minutes=int(remaining_minutes),
                )
                timers_restored += 1

            if pending_requests:
                logger.info(
                    f"Restored {len(pending_requests)} pending verifications "
                    f"({timers_restored} timers)"
                )

    async def cog_unload(self) -> None:
        """Stop tasks when unloading the cog."""
        if self._health_check_started:
            self.health_check_loop.cancel()
            self._health_check_started = False

        # Cancel all pending screenshot timers
        for _, task in list(self._screenshot_timers.items()):
            if not task.done():
                task.cancel()
        self._screenshot_timers.clear()

    def start_screenshot_timer(
        self,
        request_id: int,
        guild_id: int,
        user_id: int,
        timeout_minutes: int,
    ) -> None:
        """Start timer for screenshot timeout.

        Args:
            request_id: Request ID
            guild_id: Server ID
            user_id: User ID
            timeout_minutes: Minutes before auto-rejection
        """
        # Cancel existing timer if any
        self.cancel_screenshot_timer(request_id)

        # Create new timer
        task = asyncio.create_task(
            self._screenshot_timer_task(
                request_id=request_id,
                guild_id=guild_id,
                user_id=user_id,
                timeout_minutes=timeout_minutes,
            )
        )
        self._screenshot_timers[request_id] = task
        logger.info(f"Screenshot timer started for request {request_id} ({timeout_minutes} min)")

    def cancel_screenshot_timer(self, request_id: int) -> bool:
        """Cancel screenshot timer for a request.

        Args:
            request_id: Request ID

        Returns:
            bool: True if cancelled, False if it didn't exist
        """
        task = self._screenshot_timers.pop(request_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"Screenshot timer cancelled for request {request_id}")
            return True
        return False

    async def _screenshot_timer_task(
        self,
        request_id: int,
        guild_id: int,
        user_id: int,
        timeout_minutes: int,
    ) -> None:
        """Task that auto-rejects the request after timeout.

        Args:
            request_id: Request ID
            guild_id: Server ID
            user_id: User ID
            timeout_minutes: Timeout minutes
        """
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else f"Guild {guild_id}"
        try:
            await asyncio.sleep(timeout_minutes * 60)
            await self._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=guild_id,
                user_id=user_id,
            )
        except asyncio.CancelledError:
            logger.debug(f"[{guild_name}] Screenshot timer cancelled for request {request_id}")
        except Exception as e:
            logger.error(f"[{guild_name}] Error in screenshot timer for request {request_id}: {e}")
        finally:
            self._screenshot_timers.pop(request_id, None)

    async def _auto_reject_by_timeout(
        self,
        request_id: int,
        guild_id: int,
        user_id: int,
    ) -> None:
        """Automatically reject a request due to screenshot timeout.

        Args:
            request_id: Request ID
            guild_id: Server ID
            user_id: User ID
        """
        # Get guild for logs and message updates
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else f"Guild {guild_id}"

        async with self.bot.database.session() as session:
            verification_service = VerificationService(session=session)
            config_service = ConfigService(session=session)

            request = await verification_service.get_request(request_id)
            if not request:
                logger.warning(f"[{guild_name}] Request {request_id} not found for auto-rejection")
                return

            # Only reject if still waiting for screenshots
            if request.status != VerificationStatus.PENDING_SCREENSHOTS:
                logger.debug(
                    f"[{guild_name}] Request {request_id} no longer waiting for screenshots "
                    f"(status={request.status})"
                )
                return

            # Get config for rejection reason
            config = await config_service.get_all_config(
                guild_id=guild_id,
                cog_name=COG_NAME,
            )

            # Save previous status text before updating
            previous_status = (
                config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "⏳ Awaiting screenshots"
            )

            # Reject the request
            reason = config.get(ConfigKey.REJECT_SCREENSHOT_TIMEOUT) or "Screenshot timeout"
            await verification_service.reject(
                request_id=request_id,
                reviewer_id=self.bot.user.id if self.bot.user else 0,
                reviewer_username="Auto",
                reason=reason,
                guild_name=guild_name,
            )
            # Flush so changes are visible in subsequent queries
            await session.flush()

            # Clean from memory
            if user_id in self._pending_dm_verifications:
                del self._pending_dm_verifications[user_id]
            if not guild:
                await session.commit()
                return

            # Update moderation message
            rejected_status = format_message(
                template=config.get(ConfigKey.STATUS_REJECTED),
                moderator="Auto",
                reason=reason,
            )
            await update_mod_message_status(
                guild=guild,
                request=request,
                config=config,
                status=rejected_status,
                color=discord.Color.red(),
                previous_statuses=[previous_status],
            )

            # Notify the user
            member = guild.get_member(user_id)
            if member:
                verification_type = VerificationType(request.verification_type)
                type_display = get_verification_type_display(
                    verification_type=verification_type,
                    config=config,
                )
                rejection_msg = format_message(
                    template=config.get(ConfigKey.REJECTION_MESSAGE),
                    username=request.username,
                    server_name=guild.name,
                    verification_type=type_display,
                    reason=reason,
                )
                try:
                    await member.send(rejection_msg)
                except discord.Forbidden:
                    pass

            # Update tracker
            await update_tracker_message(
                guild=guild,
                config=config,
                verification_service=verification_service,
                config_service=config_service,
            )
            await session.commit()

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

    # Configuration keys that require updating the panel
    _PANEL_UPDATE_KEYS = frozenset(
        {
            ConfigKey.VERIFICATION_ENABLED,
            ConfigKey.VERIFICATION_CHANNEL,
            ConfigKey.MOD_NOTIFICATION_CHANNEL,
            ConfigKey.VERIFY_BUTTON_TEXT,
            ConfigKey.VERIFY_ALLY_BUTTON_TEXT,
            ConfigKey.VERIFICATION_PANEL_MESSAGE,
            ConfigKey.VERIFICATION_DISABLED_MESSAGE,
        }
    )

    # Configuration keys that require updating moderation embeds
    _MOD_EMBED_UPDATE_KEYS = frozenset(
        {
            ConfigKey.MOD_EMBED_REGULAR,
            ConfigKey.MOD_EMBED_ALLY,
            ConfigKey.STATUS_AWAITING_SCREENSHOTS,
            ConfigKey.STATUS_PENDING_REVIEW,
            ConfigKey.ACCEPT_BUTTON_TEXT,
            ConfigKey.REJECT_BUTTON_TEXT,
            ConfigKey.PLAYER_INFO_SECTIONS,
            ConfigKey.HISTORY_LABEL,
        }
    )

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Handle configuration changes from the web dashboard.

        Only updates panel and embeds once even if multiple options change.

        Args:
            guild (discord.Guild): Guild where configuration changed
            keys (list[str]): List of configuration keys that changed
        """
        keys_set = set(keys)

        # Check if any panel key changed
        if keys_set & self._PANEL_UPDATE_KEYS:
            changed_panel_keys = keys_set & self._PANEL_UPDATE_KEYS
            logger.info(f"[{guild.name}] Config changed {changed_panel_keys}, updating panel")
            await self._check_verification_message(guild=guild, recreate=True)

        # Check if any mod embed key changed
        if keys_set & self._MOD_EMBED_UPDATE_KEYS:
            changed_embed_keys = keys_set & self._MOD_EMBED_UPDATE_KEYS
            logger.info(f"[{guild.name}] Config changed {changed_embed_keys}, updating embeds")
            await self._rebuild_pending_embeds_for_guild(guild)

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Handle when the cog is enabled or disabled.

        Args:
            guild (discord.Guild): Guild where state changed
            enabled (bool): True if enabled, False if disabled
        """
        if enabled:
            logger.info(f"[{guild.name}] Cog enabled, creating panel")
            await self._check_verification_message(guild=guild, recreate=True)
            return

        logger.info(f"[{guild.name}] Cog disabled, removing panel")

        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

            panel_message_id = config.get(ConfigKey.PANEL_MESSAGE_ID)
            panel_channel_id = config.get(ConfigKey.PANEL_CHANNEL_ID)

            if not panel_message_id or not panel_channel_id:
                return

            await delete_message(
                guild=guild,
                channel_id=panel_channel_id,
                message_id=panel_message_id,
            )

            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.PANEL_MESSAGE_ID,
                value=None,
            )
            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.PANEL_CHANNEL_ID,
                value=None,
            )
            await session.commit()

    @tasks.loop(minutes=1)
    async def health_check_loop(self) -> None:
        """Periodically verify that verification panels exist.

        Each guild has its own configured interval. This loop runs
        every minute and checks if each guild is ready for its health check.
        """
        await self._run_health_check()

    @health_check_loop.before_loop
    async def before_health_check(self) -> None:
        """Wait for the bot to be ready before starting health check."""
        await self.bot.wait_until_ready()
        # Clean verifications from users who left while the bot was offline
        await self._cleanup_stale_verifications()
        # Initialize trackers for guilds with pending verifications
        await self._initialize_trackers()
        # Execute immediately on startup for all guilds
        await self._run_health_check(force_all=True)

    async def _cleanup_stale_verifications(self) -> None:
        """Cancel verifications from users who left while the bot was offline."""
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending = await service.get_all_pending()

            if not pending:
                logger.debug("No pending verifications to clean")
                return

            logger.info(f"Checking {len(pending)} pending requests...")
            config_service = ConfigService(session=session)
            cancelled_count = 0
            guilds_with_changes: dict[int, tuple[discord.Guild, dict[str, Any]]] = {}

            for request in pending:
                guild = self.bot.get_guild(request.guild_id)
                if not guild:
                    logger.warning(
                        f"[Guild ID: {request.guild_id}] Guild not found for "
                        f"request {request.id} (user={request.username})"
                    )
                    continue

                member = guild.get_member(request.user_id)
                if member:
                    logger.debug(f"[{guild.name}] User {request.username} still in server")
                    continue

                # Get config first to determine previous status text
                config = await config_service.get_all_config(
                    guild_id=request.guild_id,
                    cog_name=COG_NAME,
                )

                # Build list of all possible previous statuses
                # Status could be "awaiting screenshots", "pending review", or "ready for approval"
                awaiting_status = (
                    config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "⏳ Awaiting screenshots"
                )
                pending_review_status = (
                    config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
                )
                ready_for_approval_status = get_ready_for_approval_status(
                    config=config, guild=guild
                )

                # User not in server, cancel verification
                await service.cancel(request_id=request.id, guild_name=guild.name)

                # Clean from memory if it was pending
                if request.user_id in self._pending_dm_verifications:
                    del self._pending_dm_verifications[request.user_id]

                # Update moderation message
                try:
                    await update_mod_message_cancelled(
                        guild=guild,
                        request=request,
                        config=config,
                        previous_statuses=[
                            ready_for_approval_status,
                            pending_review_status,
                            awaiting_status,
                        ],
                    )
                except Exception as e:
                    logger.error(f"[{guild.name}] Error updating mod message: {e}")

                # Mark guild for tracker update
                guilds_with_changes[guild.id] = (guild, config)

                cancelled_count += 1
                logger.info(
                    f"[{guild.name}] Verification {request.id} cancelled "
                    f"(user {request.username} no longer in server)"
                )

            if cancelled_count > 0:
                await session.commit()

                # Update trackers for affected guilds
                for guild, config in guilds_with_changes.values():
                    try:
                        await update_tracker_message(
                            guild=guild,
                            config=config,
                            verification_service=service,
                            config_service=config_service,
                        )
                    except Exception as e:
                        logger.error(f"Error updating tracker in {guild.name}: {e}")
                await session.commit()

            logger.info(
                f"Cleanup completed: {cancelled_count}/{len(pending)} verifications cancelled"
            )

    async def _initialize_trackers(self) -> None:
        """Initialize tracker messages for guilds with pending verifications.

        Runs on bot startup to ensure trackers exist for all guilds
        that have pending verifications.
        """
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            config_service = ConfigService(session=session)

            # Get all unique guild_ids with pending verifications
            pending = await service.get_all_pending()
            if not pending:
                logger.debug("No pending verifications to initialize trackers")
                return

            # Group by guild_id
            guild_ids = {request.guild_id for request in pending}
            logger.info(f"Initializing trackers for {len(guild_ids)} guilds...")

            for guild_id in guild_ids:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                # Check if cog is enabled
                if not await self._is_cog_enabled(guild_id):
                    continue

                config = await config_service.get_all_config(
                    guild_id=guild_id,
                    cog_name=COG_NAME,
                )

                try:
                    await update_tracker_message(
                        guild=guild,
                        config=config,
                        verification_service=service,
                        config_service=config_service,
                    )
                except Exception as e:
                    logger.error(f"Error initializing tracker in {guild.name}: {e}")

            await session.commit()
            logger.info("Tracker initialization completed")

    async def _rebuild_pending_embeds_for_guild(self, guild: discord.Guild) -> None:
        """Rebuild pending verification embeds for a specific guild.

        Called when moderation embed configuration changes.

        Args:
            guild: Guild where to rebuild embeds
        """
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending = await service.get_pending_with_mod_messages()

            # Filter only this guild's requests
            guild_requests = [r for r in pending if r.guild_id == guild.id]
            logger.debug(
                f"[{guild.name}] Verifications with mod embed: "
                f"{len(guild_requests)} of {len(pending)} total"
            )
            if not guild_requests:
                return

            config_service = ConfigService(session=session)
            config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

            mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
            if not mod_channel_id:
                return

            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
                return

            rebuilt_count = 0
            for i, request in enumerate(guild_requests):
                # Add delay between edits to avoid rate limiting (5 edits/5s per channel)
                if i > 0:
                    await asyncio.sleep(1.2)

                try:
                    rebuilt = await self._rebuild_single_embed(
                        guild=guild,
                        channel=mod_channel,
                        request=request,
                        config=config,
                    )
                    if rebuilt:
                        rebuilt_count += 1
                except Exception as e:
                    logger.error(
                        f"[{guild.name}] Error rebuilding embed for request {request.id}: {e}"
                    )

            logger.debug(
                f"[{guild.name}] Rebuild completed: {rebuilt_count}/{len(guild_requests)} embeds"
            )

    async def _rebuild_single_embed(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        request: Any,
        config: dict[str, Any],
    ) -> bool:
        """Rebuild a single pending verification embed.

        Regenerates the template with current configuration while preserving
        any extra content (like OCR results) that appears after the status line.

        Args:
            guild: Guild where the message is
            channel: Moderation channel
            request: Verification request
            config: Cog configuration

        Returns:
            bool: True if rebuilt successfully
        """
        if not request.mod_message_id:
            return False

        try:
            mod_message = await channel.fetch_message(request.mod_message_id)
        except discord.NotFound:
            logger.warning(f"[{guild.name}] Mod message not found: {request.mod_message_id}")
            return False

        # Extract extra content (after the status line) from current embed
        extra_content = ""
        if mod_message.embeds:
            current_content = mod_message.embeds[0].description or ""

            # Find configured status lines (only pending statuses)
            status_texts = [
                config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "",
                config.get(ConfigKey.STATUS_PENDING_REVIEW) or "",
                config.get(ConfigKey.STATUS_READY_FOR_APPROVAL) or "",
            ]
            status_texts = [s for s in status_texts if s]  # Filter empty

            # Find the last position of any status text
            last_status_end = -1
            for status_text in status_texts:
                if status_text in current_content:
                    pos = current_content.rfind(status_text)
                    end_pos = pos + len(status_text)
                    if end_pos > last_status_end:
                        last_status_end = end_pos

            # If there's content after status, preserve it
            if last_status_end > 0 and last_status_end < len(current_content):
                extra_content = current_content[last_status_end:].strip()

        # Regenerate template with current configuration
        verification_type = VerificationType(request.verification_type)
        type_display = get_verification_type_display(
            verification_type=verification_type, config=config
        )

        # Determine status based on request status
        if request.status == VerificationStatus.PENDING_SCREENSHOTS:
            status_text = config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or ""
        else:
            status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""

        # Get user mention
        member = guild.get_member(request.user_id)
        user_mention = member.mention if member else f"<@{request.user_id}>"

        # Build additional sections (player info + history)
        async with self.bot.database.session() as session:
            verification_service = VerificationService(session=session)
            history = await verification_service.get_user_history(
                guild_id=request.guild_id,
                user_id=request.user_id,
            )
        past_requests = [r for r in history if r.id != request.id]
        additional_sections, sections_context = build_mod_embed_sections(
            config=config,
            player_info=request.player_info,
            past_requests=past_requests,
        )

        # Create new embeds with current configuration
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"
        user_display_name = member.display_name if member else request.username
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=user_mention,
            user_display_name=user_display_name,
            user_id=request.user_id,
            status=status_text,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            additional_content=extra_content,
            additional_sections=additional_sections,
            sections_context=sections_context,
            api_status="",
        )

        # Keep screenshot embeds (identified by having an image)
        # Screenshot embeds have set_image with screenshot URLs
        screenshot_embeds = [e for e in mod_message.embeds if e.image and e.image.url]
        all_embeds = [*main_embeds, *screenshot_embeds]

        # Only add buttons if pending review (already has screenshots)
        view: ModReviewView | None = None
        if request.status == VerificationStatus.PENDING_REVIEW:
            accept_label = format_message(
                template=config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
                verification_type=type_display,
            )
            reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject"
            view = ModReviewView(
                public_id=request.public_id,
                accept_label=accept_label,
                reject_label=reject_label,
            )

        await mod_message.edit(embeds=all_embeds, view=view)
        logger.debug(f"[{guild.name}] Embed rebuilt for request {request.id}")
        return True

    async def _run_health_check(self, force_all: bool = False) -> None:
        """Run panel health check on guilds that are ready.

        Args:
            force_all (bool): If True, executes for all guilds ignoring intervals
        """
        now = datetime.now(UTC)

        for guild in self.bot.guilds:
            try:
                # Get configured interval for this guild
                interval = await self._get_health_check_interval(guild.id)

                # If interval is 0, health check disabled for this guild
                if interval == 0:
                    continue

                # Check if it's time to execute (unless forced)
                if not force_all:
                    last_check = self._last_health_check.get(guild.id)
                    if last_check:
                        seconds_since_last = (now - last_check).total_seconds()
                        if seconds_since_last < interval * 60:
                            continue  # Not time yet

                # Execute health check and record timestamp
                await self._check_verification_message(guild=guild)
                self._last_health_check[guild.id] = now

            except Exception as e:
                logger.error(f"[{guild.name}] Error in health check: {e}")

    async def _get_health_check_interval(self, guild_id: int) -> int:
        """Get the configured health check interval for a guild.

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
                key=ConfigKey.HEALTH_CHECK_INTERVAL,
            )
            return interval if interval is not None else 30

    async def _get_all_config(
        self,
        guild_id: int,
        config_service: ConfigService | None = None,
    ) -> dict[str, Any]:
        """Get all cog configuration for a guild.

        Args:
            guild_id (int): Guild ID
            config_service (ConfigService | None): Existing service to reuse session

        Returns:
            dict[str, Any]: Dictionary with all configuration
        """
        if config_service:
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)
        async with self.bot.database.session() as session:
            svc = ConfigService(session=session)
            return await svc.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    def _format_message(self, template: str | None = None, **kwargs: str | None) -> str:
        """Replace placeholders in a message.

        Args:
            template (str | None): Message template
            **kwargs: Placeholders to replace (e.g.: username="John", status="Pending")

        Returns:
            str: Formatted message
        """
        return format_message(template, **kwargs)

    def _create_panel_embed(self, text: str) -> discord.Embed:
        """Create an embed for the verification panel.

        Args:
            text (str): Message text that may contain image URLs

        Returns:
            discord.Embed: Embed with formatted message
        """
        return create_panel_embed(text)

    def _get_mod_channel(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
    ) -> discord.TextChannel | None:
        """Get moderation channel if configured and accessible.

        Args:
            guild (discord.Guild): Guild
            config (dict[str, Any]): Cog configuration

        Returns:
            discord.TextChannel | None: Moderation channel or None if not available
        """
        return get_mod_channel(guild=guild, config=config, bot_user=self.bot.user)

    async def _check_verification_message(
        self,
        guild: discord.Guild,
        recreate: bool = False,
    ) -> None:
        """Verify and restore verification panel for a guild.

        Args:
            guild (discord.Guild): Guild to verify
            recreate (bool): If True, deletes existing panel and recreates it
        """
        await check_verification_message(cog=self, guild=guild, recreate=recreate)

    async def _create_verification_message(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        config: dict[str, Any],
        config_service: ConfigService,
        session: Any,
    ) -> None:
        """Create verification panel in a channel.

        Args:
            guild (discord.Guild): Panel guild
            channel (discord.TextChannel): Channel where to create
            config (dict[str, Any]): Cog configuration
            config_service (ConfigService): Config service
            session (Any): Database session
        """
        from discord_bot.verification.panel import create_verification_message

        await create_verification_message(
            cog=self,
            guild=guild,
            channel=channel,
            config=config,
            config_service=config_service,
            session=session,
        )

    async def _update_mod_message_for_review(
        self,
        channel: discord.TextChannel,
        request: Any,
        verification_service: VerificationService,
        config: dict[str, Any],
    ) -> None:
        """Update moderation message when screenshots are received.

        Args:
            channel (discord.TextChannel): Moderation channel
            request (VerificationRequest): Verification request
            verification_service (VerificationService): Verification service
            config (dict[str, Any]): Cog configuration
        """
        from discord_bot.verification.handlers import update_mod_message_for_review

        await update_mod_message_for_review(
            cog=self,
            channel=channel,
            request=request,
            verification_service=verification_service,
            config=config,
        )

    async def _validate_mod_action(
        self,
        interaction: discord.Interaction,
        public_id: str,
        session: Any,
        permission_error_key: ConfigKey,
        permission_error_default: str,
    ) -> Any:
        """Validate and prepare context for moderation actions.

        Args:
            interaction (discord.Interaction): Moderator interaction
            public_id (str): Public request ID (NanoID)
            session (AsyncSession): Database session
            permission_error_key (ConfigKey): Error message key
            permission_error_default (str): Default message

        Returns:
            ModActionContext | None: Validated context or None if failed
        """
        from discord_bot.verification.handlers import validate_mod_action

        return await validate_mod_action(
            cog=self,
            interaction=interaction,
            public_id=public_id,
            session=session,
            permission_error_key=permission_error_key,
            permission_error_default=permission_error_default,
        )

    async def handle_verification_start(
        self, interaction: discord.Interaction, verification_type: VerificationType
    ) -> None:
        """Handle verification start when user clicks a button.

        Args:
            interaction (discord.Interaction): User interaction
            verification_type (VerificationType): Verification type
        """
        await handle_verification_start(
            cog=self, interaction=interaction, verification_type=verification_type
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle DM messages with screenshots.

        Args:
            message (discord.Message): Received message
        """
        if message.guild is not None:
            return
        if message.author.bot:
            return

        # Find pending verification in memory or database
        verification_info = await self._get_pending_verification(message.author.id)

        if verification_info is None:
            await self._respond_no_pending_verification(message)
            return

        guild_id, request_id = verification_info

        # Check if cog is enabled
        if not await self._is_cog_enabled(guild_id):
            return

        await handle_dm_screenshots(
            cog=self, message=message, guild_id=guild_id, request_id=request_id
        )

    async def _get_pending_verification(self, user_id: int) -> tuple[int, int] | None:
        """Get pending verification for a user.

        Searches first in memory, then in database.
        If found in DB, restores state in memory.

        Args:
            user_id (int): User ID

        Returns:
            tuple[int, int] | None: (guild_id, request_id) or None if no pending
        """
        # First search in memory (faster)
        if user_id in self._pending_dm_verifications:
            return self._pending_dm_verifications[user_id]

        # Search in database (in case bot restarted)
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending = await service.get_any_pending_by_user(user_id)

            if pending:
                # Restore in memory for future queries
                self._pending_dm_verifications[user_id] = (pending.guild_id, pending.id)
                return (pending.guild_id, pending.id)

        return None

    async def _respond_no_pending_verification(self, message: discord.Message) -> None:
        """Respond when user sends a DM without active verification.

        Args:
            message (discord.Message): Received message
        """
        # Find a common server to get configuration
        guild_id = None
        for guild in self.bot.guilds:
            if guild.get_member(message.author.id):
                # Check if cog is enabled in this server
                if await self._is_cog_enabled(guild.id):
                    guild_id = guild.id
                    break

        # Get configured message or use default
        default_message = (
            "You don't have any verification in progress. "
            "If you want to verify, use the verification panel in the server."
        )

        if guild_id:
            config = await self._get_all_config(guild_id)
            response = config.get(ConfigKey.NO_PENDING_VERIFICATION_MESSAGE) or default_message
        else:
            response = default_message

        try:
            await message.reply(response)
        except discord.Forbidden:
            pass  # Could not reply

    async def handle_accept(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle verification approval.

        Args:
            interaction (discord.Interaction): Moderator interaction
            public_id (str): Public request ID (NanoID)
        """
        await handle_accept(cog=self, interaction=interaction, public_id=public_id)

    async def show_rejection_select(self, interaction: discord.Interaction, public_id: str) -> None:
        """Show rejection reason selector.

        Args:
            interaction (discord.Interaction): Moderator interaction
            public_id (str): Public request ID (NanoID)
        """
        await show_rejection_select(cog=self, interaction=interaction, public_id=public_id)

    async def handle_reject(
        self, interaction: discord.Interaction, public_id: str, reason: str
    ) -> None:
        """Handle verification rejection.

        Args:
            interaction (discord.Interaction): Moderator interaction
            public_id (str): Public request ID (NanoID)
            reason (str): Rejection reason
        """
        await handle_reject(cog=self, interaction=interaction, public_id=public_id, reason=reason)

    async def handle_review(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle auto-rejected verification review.

        Args:
            interaction (discord.Interaction): Moderator interaction
            public_id (str): Public request ID (NanoID)
        """
        await handle_review(cog=self, interaction=interaction, public_id=public_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Cancel pending verifications when a user leaves.

        Args:
            member (discord.Member): Member who left
        """
        if member.id in self._pending_dm_verifications:
            del self._pending_dm_verifications[member.id]

        async with self.bot.database.session() as session:
            verification_service = VerificationService(session=session)
            pending = await verification_service.get_pending_by_user(
                guild_id=member.guild.id, user_id=member.id
            )
            if pending:
                # Get config first to determine previous status text
                config_service = ConfigService(session=session)
                config = await config_service.get_all_config(
                    guild_id=member.guild.id, cog_name=COG_NAME
                )

                # Build list of all possible previous statuses
                awaiting_status = (
                    config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "⏳ Awaiting screenshots"
                )
                pending_review_status = (
                    config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
                )
                ready_for_approval_status = get_ready_for_approval_status(
                    config=config, guild=member.guild
                )

                await verification_service.cancel(
                    request_id=pending.id, guild_name=member.guild.name
                )
                await session.commit()

                # Update moderation message
                await update_mod_message_cancelled(
                    guild=member.guild,
                    request=pending,
                    config=config,
                    previous_statuses=[
                        ready_for_approval_status,
                        pending_review_status,
                        awaiting_status,
                    ],
                )

                # Update tracker message
                await update_tracker_message(
                    guild=member.guild,
                    config=config,
                    verification_service=verification_service,
                    config_service=config_service,
                )
                await session.commit()

                logger.info(
                    f"[{member.guild.name}] Verification cancelled: "
                    f"user={member.name} (left the server)"
                )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle moderation button interactions with dynamic IDs.

        The accept/reject buttons have dynamic custom_ids like
        'verification:accept:123' that include the request_id. This listener
        is the only handler for these buttons (they don't have callbacks in the view),
        which allows them to work even after restarting the bot.

        Args:
            interaction (discord.Interaction): Received interaction
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id: str = str(interaction.data.get("custom_id", "") if interaction.data else "")

        # Handle accept button: verification:accept:{public_id}
        if custom_id.startswith("verification:accept:"):
            public_id = custom_id.split(":")[2]
            await self.handle_accept(interaction=interaction, public_id=public_id)
            return

        # Handle reject button: verification:reject:{public_id}
        if custom_id.startswith("verification:reject:"):
            public_id = custom_id.split(":")[2]
            await self.show_rejection_select(interaction=interaction, public_id=public_id)
            return

        # Handle auto-reject review button: verification:review:{public_id}
        if custom_id.startswith("verification:review:"):
            public_id = custom_id.split(":")[2]
            await self.handle_review(interaction=interaction, public_id=public_id)
            return


async def setup(bot: DiscordBot) -> None:
    """Load the verification cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().register_schema(VERIFICATION_CONFIG_SCHEMA)
    await bot.add_cog(VerificationCog(bot))


async def teardown(bot: DiscordBot) -> None:
    """Unload the verification cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().unregister_schema("verification")
