"""Moderation message status updates and tracker management.

The screenshot-received update (auto/manual review) lives in ``mod_review``.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

from discord_bot.common.services.config_service import ConfigService
from discord_bot.verification.config import COG_NAME
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    create_tracker_embed,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import ModReviewView

logger = logging.getLogger(__name__)

# Status indicators for check results
STATUS_PASSED = "✅"
STATUS_FAILED = "❌"
STATUS_DISABLED = "⏸️"


def build_initial_check_statuses() -> dict[str, str]:
    """Build check status placeholders for a request whose checks have not run yet.

    Used when creating or rebuilding the moderation embed without an API
    response: every check shows the disabled/not-run indicator so the
    *_status placeholders never leak literally into the embed.

    Returns:
        dict[str, str]: All status placeholders set to the disabled indicator.
    """
    return {
        "faction_status": STATUS_DISABLED,
        "shard_status": STATUS_DISABLED,
        "regiment_status": STATUS_DISABLED,
        "name_status": STATUS_DISABLED,
        "time_status": STATUS_DISABLED,
        "steam_status": STATUS_DISABLED,
    }


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

    if config.get(ConfigKey.DELETE_PROCESSED_MESSAGES):
        # Only deleting: a partial message spares fetching it first
        try:
            await mod_channel.get_partial_message(request.mod_message_id).delete()
        except discord.NotFound:
            logger.warning(f"[{guild.name}] Mod message not found: {request.mod_message_id}")
        return

    try:
        mod_message = await mod_channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"[{guild.name}] Mod message not found: {request.mod_message_id}")
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
    original_rejection_reason: str | None = None,
) -> None:
    """Update moderation message for manual review.

    Reverts an auto-rejected verification back to pending review state,
    re-adding the accept/reject buttons.

    Args:
        guild (discord.Guild): Guild where the message is.
        request (VerificationRequest): Verification request.
        config (dict[str, Any]): Cog configuration.
        public_id (str): Public request ID (NanoID).
        original_rejection_reason (str | None): Original rejection reason before
            it was cleared by revert_to_pending_review. If not provided, falls
            back to request.rejection_reason.
    """
    # Build the previous status (auto-rejected)
    # Use original_rejection_reason if provided, as request.rejection_reason
    # may have been cleared by revert_to_pending_review
    rejection_reason = original_rejection_reason or request.rejection_reason or ""
    previous_status = format_message(
        template=config.get(ConfigKey.STATUS_REJECTED),
        moderator="Auto",
        moderator_display_name="Auto",
        reason=rejection_reason,
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


async def _clear_tracker_message_id(guild: discord.Guild, config_service: ConfigService) -> None:
    """Forget the stored tracker message ID of a guild.

    Args:
        guild (discord.Guild): Guild whose tracker message is gone.
        config_service (ConfigService): Config service holding the message ID.
    """
    await config_service.set_value(
        guild_id=guild.id,
        cog_name=COG_NAME,
        key=ConfigKey.TRACKER_MESSAGE_ID,
        value=None,
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

    # The tracker is only deleted or fully rewritten, so a partial message
    # is enough: this runs on every verification event and fetching it
    # first was one more request each time
    tracker_message_id = config.get(ConfigKey.TRACKER_MESSAGE_ID)
    tracker_message: discord.PartialMessage | None = None
    if tracker_message_id:
        tracker_message = mod_channel.get_partial_message(tracker_message_id)

    if not tracker_enabled or not pending_requests:
        if tracker_message:
            try:
                await tracker_message.delete()
            except discord.NotFound:
                pass
            await _clear_tracker_message_id(guild=guild, config_service=config_service)
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
            await _clear_tracker_message_id(guild=guild, config_service=config_service)

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
