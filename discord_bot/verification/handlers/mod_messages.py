"""Moderation messages and tracker management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.services.config_service import ConfigService
from discord_bot.verification.auto_processor import (
    get_auto_rejectable_failures,
    get_rejection_message,
    is_auto_reject_enabled,
    process_verification,
)
from discord_bot.verification.config import COG_NAME
from discord_bot.verification.enums import (
    AutoProcessMode,
    ConfigKey,
    RejectType,
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

# Status indicators for check results
STATUS_PASSED = "✅"
STATUS_FAILED = "❌"
STATUS_DISABLED = "⏸️"


def _build_check_statuses(
    config: dict[str, Any],
    failures: set[RejectType],
    request: VerificationRequest,
    api_response_exists: bool,
) -> dict[str, str]:
    """Build status indicators for each verification check.

    Args:
        config (dict[str, Any]): Cog configuration.
        failures (set[RejectType]): Set of failed checks.
        request (VerificationRequest): Verification request.
        api_response_exists (bool): Whether API response exists (checks ran).

    Returns:
        dict[str, str]: Status placeholders (faction_status, shard_status, etc.)
    """
    from discord_bot.verification.enums import NameMatchMode

    statuses: dict[str, str] = {}

    # Faction check - enabled if VERIFICATION_FACTION is configured
    faction_configured = bool(config.get(ConfigKey.VERIFICATION_FACTION))
    if not api_response_exists or not faction_configured:
        statuses["faction_status"] = STATUS_DISABLED
    elif RejectType.WRONG_FACTION in failures:
        statuses["faction_status"] = STATUS_FAILED
    else:
        statuses["faction_status"] = STATUS_PASSED

    # Shard check - enabled if VERIFICATION_SHARD is configured
    shard_configured = bool(config.get(ConfigKey.VERIFICATION_SHARD))
    if not api_response_exists or not shard_configured:
        statuses["shard_status"] = STATUS_DISABLED
    elif RejectType.WRONG_SHARD in failures:
        statuses["shard_status"] = STATUS_FAILED
    else:
        statuses["shard_status"] = STATUS_PASSED

    # Regiment check - only for REGULAR verification
    is_regular = request.verification_type == VerificationType.REGULAR
    if not api_response_exists or not is_regular:
        statuses["regiment_status"] = STATUS_DISABLED
    elif RejectType.HAS_REGIMENT in failures:
        statuses["regiment_status"] = STATUS_FAILED
    else:
        statuses["regiment_status"] = STATUS_PASSED

    # Name check - enabled if VERIFICATION_MATCH_NAME is not NONE
    match_mode = config.get(ConfigKey.VERIFICATION_MATCH_NAME, NameMatchMode.NONE)
    # Handle legacy boolean values
    if match_mode is True:
        name_check_enabled = True
    elif match_mode is False or not match_mode:
        name_check_enabled = False
    else:
        name_check_enabled = match_mode != NameMatchMode.NONE

    if not api_response_exists or not name_check_enabled:
        statuses["name_status"] = STATUS_DISABLED
    elif RejectType.NAME_MISMATCH in failures:
        statuses["name_status"] = STATUS_FAILED
    else:
        statuses["name_status"] = STATUS_PASSED

    # Time diff check - enabled if VERIFICATION_TIME_DIFF > 0
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    time_check_enabled = time_diff_limit and time_diff_limit > 0
    if not api_response_exists or not time_check_enabled:
        statuses["time_status"] = STATUS_DISABLED
    elif RejectType.TIME_DIFF in failures:
        statuses["time_status"] = STATUS_FAILED
    else:
        statuses["time_status"] = STATUS_PASSED

    return statuses


def _build_rejection_messages(
    config: dict[str, Any],
    failures: set[RejectType],
) -> list[str]:
    """Build rejection messages for all failures.

    Args:
        config (dict[str, Any]): Cog configuration.
        failures (set[RejectType]): Set of failure types.

    Returns:
        list[str]: List of formatted rejection messages.
    """
    messages = []
    # Process in enum order for consistent output
    for reject_type in RejectType:
        if reject_type in failures:
            format_kwargs: dict[str, Any] = {}
            if reject_type == RejectType.WRONG_SHARD:
                format_kwargs["shard"] = config.get(ConfigKey.VERIFICATION_SHARD, "")
            messages.append(
                get_rejection_message(config=config, reason=reject_type, **format_kwargs)
            )
    return messages


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

    player_info: dict[str, Any] | None = None
    failures: set[RejectType] = set()
    api_response_exists = False
    api_status = ""

    if api_result:
        if api_result.success and api_result.response:
            api_response_exists = True
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
            api_status = f"⚠️ **{reject_msg}**"
        else:
            error_msg = get_api_error_message(api_result.status_code)
            api_status = f"❌ **API Error:** {error_msg}"

    embeds = create_screenshot_embeds(url1=request.screenshot_1_url, url2=request.screenshot_2_url)

    additional_sections, sections_context = await get_embed_additional_sections(
        request=request,
        config=config,
        verification_service=verification_service,
        player_info=player_info,
    )

    auto_mode = config.get(ConfigKey.VERIFICATION_AUTOMATIC, AutoProcessMode.NONE)
    logger.debug(
        f"[{channel.guild.name}] Auto mode: {auto_mode!r} (type={type(auto_mode).__name__})"
    )
    if auto_mode is True:
        auto_mode = AutoProcessMode.BOTH
    elif auto_mode is False or not auto_mode:
        auto_mode = AutoProcessMode.NONE

    auto_reject = auto_mode in (AutoProcessMode.REJECT_ONLY, AutoProcessMode.BOTH)
    auto_approve = auto_mode in (AutoProcessMode.APPROVE_ONLY, AutoProcessMode.BOTH)
    logger.debug(f"[{channel.guild.name}] auto_reject={auto_reject}, auto_approve={auto_approve}")

    if (auto_reject or auto_approve) and api_result:
        guild = channel.guild

        if api_result.status_code == 422 and auto_reject:
            # Check if auto-reject for invalid screenshots is enabled
            if is_auto_reject_enabled(config=config, reason=RejectType.INVALID_SCREENSHOTS):
                reject_reason = get_rejection_message(
                    config=config, reason=RejectType.INVALID_SCREENSHOTS
                )
                # Build check statuses for 422 error (checks didn't run)
                check_statuses_422 = _build_check_statuses(
                    config=config,
                    failures={RejectType.INVALID_SCREENSHOTS},
                    request=request,
                    api_response_exists=False,  # No valid response, so checks didn't run
                )
                await handle_auto_rejection(
                    cog=cog,
                    guild=guild,
                    request=request,
                    verification_service=verification_service,
                    config=config,
                    mod_message=mod_message,
                    embeds=embeds,
                    reason=reject_reason,
                    additional_sections=additional_sections,
                    sections_context=sections_context,
                    check_statuses=check_statuses_422,
                    api_status=api_status,
                )
                return True

        if api_result.success and api_result.response:
            member = guild.get_member(request.user_id)
            member_display_name = member.display_name if member else request.username

            failures = process_verification(
                request=request,
                api_response=api_result.response,
                config=config,
                member_display_name=member_display_name,
            )
            should_approve = len(failures) == 0
            logger.debug(
                f"[{guild.name}] Verification result: failures={failures}, "
                f"should_approve={should_approve}, auto_reject={auto_reject}"
            )

            # Check if any failures have auto-reject enabled
            should_auto_reject = auto_reject
            auto_rejectable: set[RejectType] = set()
            if failures and auto_reject:
                auto_rejectable = get_auto_rejectable_failures(config=config, failures=failures)
                # Auto-reject if ANY failure has auto-reject enabled
                should_auto_reject = len(auto_rejectable) > 0
                logger.debug(
                    f"[{guild.name}] Auto-reject check: auto_rejectable={auto_rejectable}, "
                    f"should_auto_reject={should_auto_reject}"
                )

            # Build rejection messages - only for auto-rejectable failures if auto-rejecting
            rejection_reason: str | None = None
            if failures:
                # Use only auto-rejectable failures for the rejection message
                failures_for_message = auto_rejectable if should_auto_reject else failures
                rejection_messages = _build_rejection_messages(
                    config=config, failures=failures_for_message
                )
                rejection_reason = "\n".join(rejection_messages)

            # Build check statuses for the verification result
            check_statuses_auto = _build_check_statuses(
                config=config,
                failures=failures,
                request=request,
                api_response_exists=True,
            )

            processed = await process_auto_verification(
                cog=cog,
                guild=guild,
                request=request,
                verification_service=verification_service,
                config=config,
                mod_message=mod_message,
                embeds=embeds,
                should_approve=should_approve,
                rejection_reason=rejection_reason,
                auto_approve=auto_approve,
                auto_reject=should_auto_reject,
                additional_sections=additional_sections,
                sections_context=sections_context,
                check_statuses=check_statuses_auto,
                api_status=api_status,
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

    # Build check status placeholders
    check_statuses = _build_check_statuses(
        config=config,
        failures=failures,
        request=request,
        api_response_exists=api_response_exists,
    )

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
        additional_sections=additional_sections,
        sections_context=sections_context,
        api_status=api_status,
        **check_statuses,
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
