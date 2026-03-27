"""Panel logic and health check for the verification cog."""

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message
from discord_bot.verification.config import COG_NAME
from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.formatters import create_panel_embed, format_message
from discord_bot.verification.views import VerificationPanelView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


def get_mod_channel(
    guild: discord.Guild,
    config: dict[str, Any],
    bot_user: discord.User | discord.ClientUser | None,
) -> discord.TextChannel | None:
    """Get moderation channel if configured and accessible.

    Args:
        guild (discord.Guild): Guild.
        config (dict[str, Any]): Cog configuration.
        bot_user (discord.User | discord.ClientUser | None): Bot user.

    Returns:
        discord.TextChannel | None: Moderation channel or None if not available.
    """
    mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return None

    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return None

    # Verify bot permissions
    if bot_user is None:
        return None

    bot_member = guild.get_member(bot_user.id)
    if not bot_member:
        return None

    permissions = mod_channel.permissions_for(bot_member)
    if not permissions.send_messages:
        return None

    return mod_channel


async def check_verification_message(
    cog: "VerificationCog",
    guild: discord.Guild,
    recreate: bool = False,
) -> None:
    """Verify and restore verification panel for a guild.

    Args:
        cog (VerificationCog): Cog instance.
        guild (discord.Guild): Guild to verify.
        recreate (bool): If True, deletes existing panel and recreates it
            (used when panel configuration changes).
    """
    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)

        # Check if cog is enabled
        if not await config_service.is_cog_enabled(guild_id=guild.id, cog_name=COG_NAME):
            return

        # Get all configuration at once
        config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

        # Get configured channel
        channel_id = config.get(ConfigKey.VERIFICATION_CHANNEL)
        if not channel_id:
            return  # No channel configured

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"[{guild.name}] Verification channel (ID: {channel_id}) not found")
            return

        # Get current panel
        panel_message_id = config.get(ConfigKey.PANEL_MESSAGE_ID)
        panel_channel_id = config.get(ConfigKey.PANEL_CHANNEL_ID)

        # If recreate=True, delete old panel and create new
        if recreate:
            if panel_message_id and panel_channel_id:
                await delete_message(
                    guild=guild,
                    channel_id=panel_channel_id,
                    message_id=panel_message_id,
                )
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Case 1: No panel, create a new one
        if not panel_message_id:
            logger.info(f"[{guild.name}] Creating verification panel in #{channel.name}")
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Case 2: Channel changed, delete old panel and create new
        if panel_channel_id and panel_channel_id != channel_id:
            old_channel = guild.get_channel(panel_channel_id)
            old_channel_name = f"#{old_channel.name}" if old_channel else f"ID:{panel_channel_id}"
            logger.info(f"[{guild.name}] Moving panel from {old_channel_name} to #{channel.name}")
            await delete_message(
                guild=guild,
                channel_id=panel_channel_id,
                message_id=panel_message_id,
            )
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Case 3: Verify that the panel exists and has buttons
        try:
            message = await channel.fetch_message(panel_message_id)
            # Verify it has buttons (active view)
            if not message.components:
                logger.info(f"[{guild.name}] Panel without buttons, restoring...")
                await cog._create_verification_message(
                    guild=guild,
                    channel=channel,
                    config=config,
                    config_service=config_service,
                    session=session,
                )
        except discord.NotFound:
            logger.info(f"[{guild.name}] Panel not found, restoring...")
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] No permission to verify panel")


async def create_verification_message(
    cog: "VerificationCog",
    guild: discord.Guild,
    channel: discord.TextChannel,
    config: dict[str, Any],
    config_service: ConfigService,
    session: Any,
) -> None:
    """Create verification panel in a channel.

    Args:
        cog (VerificationCog): Cog instance.
        guild (discord.Guild): Panel guild.
        channel (discord.TextChannel): Channel where to create.
        config (dict[str, Any]): Cog configuration.
        config_service (ConfigService): Config service (for set_value).
        session (Any): Database session.
    """
    # Check if verification is enabled
    verification_enabled = config.get(ConfigKey.VERIFICATION_ENABLED)
    if verification_enabled is False:
        logger.info(f"[{guild.name}] Verification manually disabled")

    # Verify that moderation channel is configured and accessible
    mod_channel = get_mod_channel(guild=guild, config=config, bot_user=cog.bot.user)
    if not mod_channel:
        logger.warning(
            f"[{guild.name}] Verification disabled: "
            f"moderation channel not configured or no permissions"
        )

    is_configured = verification_enabled is not False and mod_channel is not None

    if is_configured:
        # Verification enabled - show buttons
        formatted_message = format_message(
            template=config.get(ConfigKey.VERIFICATION_PANEL_MESSAGE),
            server_name=guild.name,
        )
        view: discord.ui.View | None = VerificationPanelView(
            verify_label=config.get(ConfigKey.VERIFY_BUTTON_TEXT) or "Verify",
            ally_label=config.get(ConfigKey.VERIFY_ALLY_BUTTON_TEXT) or "Verify as Ally",
        )
    else:
        # Verification disabled - show message without buttons
        formatted_message = format_message(
            template=config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE),
            server_name=guild.name,
        )
        view = None

    # Create embed for the message
    embed = create_panel_embed(formatted_message)

    try:
        if view:
            new_message = await channel.send(embed=embed, view=view)
        else:
            new_message = await channel.send(embed=embed)
        await config_service.set_value(
            guild_id=guild.id,
            cog_name=COG_NAME,
            key=ConfigKey.PANEL_MESSAGE_ID,
            value=new_message.id,
        )
        await config_service.set_value(
            guild_id=guild.id,
            cog_name=COG_NAME,
            key=ConfigKey.PANEL_CHANNEL_ID,
            value=channel.id,
        )
        await session.commit()
        logger.info(f"[{guild.name}] Verification panel created in #{channel.name}")
    except discord.Forbidden:
        logger.error(f"[{guild.name}] No permission to send panel in #{channel.name}")
