"""Moderation messages and tracker management."""

import logging
import re
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.verification.config import COG_NAME
from discord_bot.verification.enums import (
    AutoProcessMode,
    ConfigKey,
    VerificationType,
)
from discord_bot.verification.formatters import (
    create_mod_embeds,
    create_tracker_embed,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers.auto_processing import (
    handle_auto_rejection,
    process_auto_verification,
    send_mod_ping_message,
)
from discord_bot.verification.handlers.utils import (
    create_screenshot_embeds,
    get_api_error_message,
    get_embed_additional_sections,
    get_ready_for_approval_status,
)
from discord_bot.verification.views import ModReviewView

if TYPE_CHECKING:
    from discord_bot.common.services.config_service import ConfigService
    from discord_bot.verification.api_client import VerificationAPIResult
    from discord_bot.verification.cog import VerificationCog
    from discord_bot.verification.models import VerificationRequest
    from discord_bot.verification.service import VerificationService

logger = logging.getLogger(__name__)


async def update_mod_message_for_review(
    cog: "VerificationCog",
    channel: discord.TextChannel,
    request: "VerificationRequest",
    verification_service: "VerificationService",
    config: dict[str, Any],
    api_result: "VerificationAPIResult | None" = None,
) -> bool:
    """Update moderation message when screenshots are received.

    Args:
        cog: Cog instance.
        channel: Moderation channel.
        request: Verification request.
        verification_service: Verification service.
        config: Cog configuration.
        api_result: Verification API result.

    Returns:
        True if auto-approval/rejection was performed, False if manual review required.
    """
    from discord_bot.verification.auto_processor import process_verification

    if not request.mod_message_id:
        return False

    try:
        mod_message = await channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"[{channel.guild.name}] Mod message not found: {request.mod_message_id}")
        return False

    verification_type = VerificationType(request.verification_type)
    type_display = get_verification_type_display(verification_type=verification_type, config=config)
    status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
    created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"

    additional_content = ""
    player_info: dict[str, Any] | None = None

    if api_result:
        if api_result.success and api_result.response:
            player_info = {
                "name": api_result.response.name or "N/A",
                "regiment": api_result.response.regiment or "N/A",
                "level": str(api_result.response.level)
                if api_result.response.level is not None
                else "N/A",
                "faction": api_result.response.faction or "N/A",
                "shard": api_result.response.shard or "N/A",
                "time": api_result.response.ingame_time or "N/A",
                "war": str(api_result.response.war)
                if api_result.response.war is not None
                else "N/A",
                "war_time": api_result.response.current_ingame_time or "N/A",
            }
            await verification_service.set_player_info(
                request_id=request.id,
                player_info=player_info,
            )
        elif api_result.status_code == 422:
            reject_msg = config.get(ConfigKey.REJECT_WRONG_CAPTURES) or "Invalid captures"
            additional_content += f"\n\n⚠️ **{reject_msg}**"
        else:
            error_msg = get_api_error_message(api_result.status_code)
            additional_content += f"\n\n❌ **API Error:** {error_msg}"

    embeds = create_screenshot_embeds(url1=request.screenshot_1_url, url2=request.screenshot_2_url)

    additional_sections, sections_context = await get_embed_additional_sections(
        request=request,
        config=config,
        verification_service=verification_service,
        player_info=player_info,
    )

    auto_mode = config.get(ConfigKey.VERIFICATION_AUTOMATIC, AutoProcessMode.NONE)
    if auto_mode is True:
        auto_mode = AutoProcessMode.BOTH
    elif auto_mode is False or not auto_mode:
        auto_mode = AutoProcessMode.NONE

    auto_reject = auto_mode in (AutoProcessMode.REJECT_ONLY, AutoProcessMode.BOTH)
    auto_approve = auto_mode in (AutoProcessMode.APPROVE_ONLY, AutoProcessMode.BOTH)

    if (auto_reject or auto_approve) and api_result:
        guild = channel.guild

        if api_result.status_code == 422 and auto_reject:
            reject_reason = config.get(ConfigKey.REJECT_WRONG_CAPTURES) or "Invalid captures"
            await handle_auto_rejection(
                cog=cog,
                guild=guild,
                request=request,
                verification_service=verification_service,
                config=config,
                mod_message=mod_message,
                additional_content=additional_content,
                embeds=embeds,
                reason=reject_reason,
                additional_sections=additional_sections,
                sections_context=sections_context,
            )
            return True

        if api_result.success and api_result.response:
            member = guild.get_member(request.user_id)
            member_display_name = member.display_name if member else request.username

            should_approve, rejection_reason = process_verification(
                request=request,
                api_response=api_result.response,
                config=config,
                member_display_name=member_display_name,
            )

            processed = await process_auto_verification(
                cog=cog,
                guild=guild,
                request=request,
                verification_service=verification_service,
                config=config,
                mod_message=mod_message,
                additional_content=additional_content,
                embeds=embeds,
                should_approve=should_approve,
                rejection_reason=rejection_reason,
                auto_approve=auto_approve,
                auto_reject=auto_reject,
                additional_sections=additional_sections,
                sections_context=sections_context,
            )
            if processed:
                return True

            if should_approve and not auto_approve:
                status_text = get_ready_for_approval_status(config=config, guild=guild)

    accept_label = format_message(
        config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject"
    view = ModReviewView(
        public_id=request.public_id, accept_label=accept_label, reject_label=reject_label
    )

    member = channel.guild.get_member(request.user_id)
    main_embeds = create_mod_embeds(
        verification_type=verification_type,
        config=config,
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        user_id=request.user_id,
        status=status_text,
        created_at=created_at_str,
        created_at_relative=created_at_relative,
        guild=channel.guild,
        member=member,
        additional_content=additional_content,
        additional_sections=additional_sections,
        sections_context=sections_context,
    )
    all_embeds = [*main_embeds, *embeds]
    await mod_message.edit(embeds=all_embeds, view=view)

    await send_mod_ping_message(channel=channel, config=config)
    return False


async def update_mod_message_status(
    guild: discord.Guild,
    request: "VerificationRequest",
    config: dict[str, Any],
    status: str,
    color: discord.Color,
    verification_service: "VerificationService | None" = None,
) -> None:
    """Update the moderation message with a new status.

    Regenerates the complete embed using request data.

    Args:
        guild: Guild where the moderation channel is
        request: Verification request
        config: Cog configuration
        status: New status text
        color: Embed color
        verification_service: Verification service (for history)
    """
    if not request.mod_message_id:
        return

    mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return

    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return

    try:
        mod_message = await mod_channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"[{guild.name}] Mod message not found: {request.mod_message_id}")
        return

    if config.get(ConfigKey.DELETE_PROCESSED_MESSAGES):
        await mod_message.delete()
        return

    verification_type = VerificationType(request.verification_type)
    created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"
    member = guild.get_member(request.user_id)

    additional_sections: list[dict[str, Any]] | None = None
    sections_context: dict[str, Any] | None = None

    if verification_service:
        additional_sections, sections_context = await get_embed_additional_sections(
            request=request,
            config=config,
            verification_service=verification_service,
        )

    main_embeds = create_mod_embeds(
        verification_type=verification_type,
        config=config,
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        user_id=request.user_id,
        status=status,
        created_at=created_at_str,
        created_at_relative=created_at_relative,
        guild=guild,
        member=member,
        additional_sections=additional_sections,
        sections_context=sections_context,
    )

    for embed in main_embeds:
        embed.color = color

    screenshot_embeds = mod_message.embeds[1:] if len(mod_message.embeds) > 1 else []
    all_embeds = [*main_embeds, *screenshot_embeds]

    await mod_message.edit(
        embeds=all_embeds,
        view=None,
    )


async def update_mod_message_cancelled(
    guild: discord.Guild,
    request: "VerificationRequest",
    config: dict[str, Any],
    verification_service: "VerificationService | None" = None,
) -> None:
    """Update the moderation message when a verification is cancelled.

    Used when a user leaves the server while having a pending verification.

    Args:
        guild: Guild where the moderation channel is
        request: Cancelled verification request
        config: Cog configuration
        verification_service: Verification service (for history)
    """
    cancelled_status = config.get(ConfigKey.STATUS_CANCELLED) or "🚫 **Status:** Cancelled"
    await update_mod_message_status(
        guild=guild,
        request=request,
        config=config,
        status=cancelled_status,
        color=discord.Color.dark_grey(),
        verification_service=verification_service,
    )


async def update_mod_message_for_manual_review(
    guild: discord.Guild,
    request: "VerificationRequest",
    config: dict[str, Any],
    public_id: str,
) -> None:
    """Update moderation message for manual review.

    Args:
        guild: Guild where the message is
        request: Verification request
        config: Cog configuration
        public_id: Public request ID (NanoID)
    """
    if not request.mod_message_id:
        return

    mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return

    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return

    try:
        mod_message = await mod_channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"[{guild.name}] Mod message not found: {request.mod_message_id}")
        return

    current_content = ""
    if mod_message.embeds:
        current_content = mod_message.embeds[0].description or ""

    pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
    rejected_status = config.get(ConfigKey.STATUS_REJECTED) or ""

    if rejected_status and rejected_status in current_content:
        new_content = current_content.replace(rejected_status, pending_status)
    else:
        pattern = r"❌[^\n]*(?:Auto|reject)[^\n]*"
        new_content = re.sub(pattern, pending_status, current_content)
        if new_content == current_content:
            new_content = current_content + f"\n\n{pending_status}"

    main_embed = mod_message.embeds[0].copy() if mod_message.embeds else discord.Embed()
    main_embed.description = new_content

    screenshot_embeds = mod_message.embeds[1:] if mod_message.embeds else []
    all_embeds = [main_embed, *screenshot_embeds]

    type_display = get_verification_type_display(
        verification_type=VerificationType(request.verification_type), config=config
    )
    accept_label = format_message(
        config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject"
    view = ModReviewView(
        public_id=public_id,
        accept_label=accept_label,
        reject_label=reject_label,
    )

    await mod_message.edit(embeds=all_embeds, view=view)


async def update_tracker_message(
    guild: discord.Guild,
    config: dict[str, Any],
    verification_service: "VerificationService",
    config_service: "ConfigService",
) -> None:
    """Update or create the pending verifications tracker message.

    This message should always be the last one in the moderation channel and
    displays a list of all pending verifications.

    Args:
        guild: Guild where the moderation channel is
        config: Cog configuration
        verification_service: Verification service to get requests
        config_service: Config service to save/get message ID
    """
    tracker_title = config.get(ConfigKey.TRACKER_TITLE)
    tracker_enabled = bool(tracker_title)

    mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return

    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return

    pending_requests = await verification_service.get_pending_for_guild(guild.id)

    tracker_message_id = config.get(ConfigKey.TRACKER_MESSAGE_ID)
    tracker_message: discord.Message | None = None

    if tracker_message_id:
        try:
            tracker_message = await mod_channel.fetch_message(tracker_message_id)
        except discord.NotFound:
            tracker_message = None
            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.TRACKER_MESSAGE_ID,
                value=None,
            )

    if not tracker_enabled or not pending_requests:
        if tracker_message:
            try:
                await tracker_message.delete()
            except discord.NotFound:
                pass
            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.TRACKER_MESSAGE_ID,
                value=None,
            )
        return

    tracker_embed = create_tracker_embed(
        pending_requests=pending_requests,
        config=config,
        guild_id=guild.id,
        channel_id=mod_channel_id,
    )

    if tracker_message:
        async for last_message in mod_channel.history(limit=1):
            if last_message.id != tracker_message.id:
                try:
                    await tracker_message.delete()
                except discord.NotFound:
                    pass
                tracker_message = None
            break

    if tracker_message:
        try:
            await tracker_message.edit(embed=tracker_embed)
        except discord.NotFound:
            tracker_message = None

    if not tracker_message:
        try:
            new_message = await mod_channel.send(embed=tracker_embed)
            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.TRACKER_MESSAGE_ID,
                value=new_message.id,
            )
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Could not send tracker message in #{mod_channel.name}")
