"""Moderation messages and tracker management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.services.config_service import ConfigService
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
from discord_bot.verification.models import VerificationAPIResult, VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import ModReviewView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


async def update_mod_message_for_review(
    cog: VerificationCog,
    channel: discord.TextChannel,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    api_result: VerificationAPIResult | None = None,
) -> bool:
    """Update moderation message when screenshots are received.

    Args:
        cog (VerificationCog): Cog instance.
        channel (discord.TextChannel): Moderation channel.
        request (VerificationRequest): Verification request.
        verification_service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        api_result (VerificationAPIResult | None): Verification API result.

    Returns:
        bool: True if auto-approval/rejection was performed, False if manual review.
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
                "level": str(api_result.response.level),
                "faction": api_result.response.faction or "N/A",
                "shard": api_result.response.shard or "N/A",
                "time": api_result.response.ingame_time or "N/A",
                "war": str(api_result.response.war_number),
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
        template=config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject"
    view = ModReviewView(
        public_id=request.public_id, accept_label=accept_label, reject_label=reject_label
    )

    member = channel.guild.get_member(request.user_id)
    user_display_name = member.display_name if member else request.username
    main_embeds = create_mod_embeds(
        verification_type=verification_type,
        config=config,
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        user_display_name=user_display_name,
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


def _replace_status_text(text: str | None, old_statuses: list[str], new_status: str) -> str | None:
    """Replace old status with new status in text.

    Tries each possible old status in order until one is found and replaced.

    Args:
        text (str | None): Text that may contain the old status.
        old_statuses (list[str]): List of possible previous status texts to find.
        new_status (str): The new status text to replace with.

    Returns:
        str | None: Text with status replaced, or original text if no old_status found.
    """
    if not text:
        return text
    for old_status in old_statuses:
        if old_status and old_status in text:
            return text.replace(old_status, new_status)
    return text


async def update_mod_message_status(
    guild: discord.Guild,
    request: VerificationRequest,
    config: dict[str, Any],
    status: str,
    color: discord.Color,
    previous_statuses: list[str],
    view: discord.ui.View | None = None,
) -> None:
    """Update the moderation message with a new status.

    Preserves existing embed content and only updates the status text
    and color. Finds the previous status text and replaces it with the
    new status. This handles the case where the user has left the server
    and their member object is no longer available.

    Args:
        guild (discord.Guild): Guild where the moderation channel is.
        request (VerificationRequest): Verification request.
        config (dict[str, Any]): Cog configuration.
        status (str): New status text.
        color (discord.Color): Embed color.
        previous_statuses (list[str]): Possible previous status texts to find and replace.
        view (discord.ui.View | None): View to attach, or None to remove buttons.
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

    if not mod_message.embeds:
        return

    main_embed = mod_message.embeds[0].copy()

    # Replace status in description
    main_embed.description = _replace_status_text(
        text=main_embed.description,
        old_statuses=previous_statuses,
        new_status=status,
    )

    # Replace status in title
    main_embed.title = _replace_status_text(
        text=main_embed.title,
        old_statuses=previous_statuses,
        new_status=status,
    )

    # Replace status in all fields
    for i, field in enumerate(main_embed.fields):
        new_name = _replace_status_text(
            text=field.name,
            old_statuses=previous_statuses,
            new_status=status,
        )
        new_value = _replace_status_text(
            text=field.value,
            old_statuses=previous_statuses,
            new_status=status,
        )
        if new_name != field.name or new_value != field.value:
            main_embed.set_field_at(
                index=i,
                name=new_name or field.name,
                value=new_value or field.value,
                inline=field.inline,
            )

    main_embed.color = color

    # Keep screenshot embeds
    screenshot_embeds = mod_message.embeds[1:] if len(mod_message.embeds) > 1 else []
    all_embeds = [main_embed, *screenshot_embeds]

    await mod_message.edit(
        embeds=all_embeds,
        view=view,
    )


async def update_mod_message_cancelled(
    guild: discord.Guild,
    request: VerificationRequest,
    config: dict[str, Any],
    previous_statuses: list[str],
) -> None:
    """Update the moderation message when a verification is cancelled.

    Used when a user leaves the server while having a pending verification.

    Args:
        guild (discord.Guild): Guild where the moderation channel is.
        request (VerificationRequest): Cancelled verification request.
        config (dict[str, Any]): Cog configuration.
        previous_statuses (list[str]): Possible previous status texts to find and replace.
    """
    cancelled_status = config.get(ConfigKey.STATUS_CANCELLED) or "🚫 **Status:** Cancelled"
    await update_mod_message_status(
        guild=guild,
        request=request,
        config=config,
        status=cancelled_status,
        color=discord.Color.dark_grey(),
        previous_statuses=previous_statuses,
    )


async def update_mod_message_for_manual_review(
    guild: discord.Guild,
    request: VerificationRequest,
    config: dict[str, Any],
    public_id: str,
) -> None:
    """Update moderation message for manual review.

    Reverts an auto-rejected verification back to pending review state,
    re-adding the accept/reject buttons.

    Args:
        guild (discord.Guild): Guild where the message is.
        request (VerificationRequest): Verification request.
        config (dict[str, Any]): Cog configuration.
        public_id (str): Public request ID (NanoID).
    """
    # Build the previous status (auto-rejected)
    previous_status = format_message(
        template=config.get(ConfigKey.STATUS_REJECTED),
        moderator="Auto",
        reason=request.rejection_reason or "",
    )

    # Build the new status (pending review)
    new_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"

    # Build the view with accept/reject buttons
    type_display = get_verification_type_display(
        verification_type=VerificationType(request.verification_type),
        config=config,
    )
    accept_label = format_message(
        template=config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject"
    view = ModReviewView(
        public_id=public_id,
        accept_label=accept_label,
        reject_label=reject_label,
    )

    await update_mod_message_status(
        guild=guild,
        request=request,
        config=config,
        status=new_status,
        color=discord.Color.orange(),
        previous_statuses=[previous_status],
        view=view,
    )


async def update_tracker_message(
    guild: discord.Guild,
    config: dict[str, Any],
    verification_service: VerificationService,
    config_service: ConfigService,
) -> None:
    """Update or create the pending verifications tracker message.

    This message should always be the last one in the moderation channel and
    displays a list of all pending verifications.

    Args:
        guild (discord.Guild): Guild where the moderation channel is.
        config (dict[str, Any]): Cog configuration.
        verification_service (VerificationService): Verification service to get requests.
        config_service (ConfigService): Config service to save/get message ID.
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
