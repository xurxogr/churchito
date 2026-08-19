"""DM intake: screenshots and Steam profile URL submitted by the user.

Screenshots and the (optional) Steam profile URL may arrive together or
across separate DMs, in any order. Each item received gets its own
acknowledgment; only once every required item is present does the
OCR/mod-notification flow proceed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import is_valid_discord_cdn_url
from discord_bot.verification.api_client import MAX_IMAGE_BYTES, call_verification_api
from discord_bot.verification.auto_processor import is_steam_profile_required
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import format_message
from discord_bot.verification.handlers.mod_messages import update_tracker_message
from discord_bot.verification.handlers.mod_review import update_mod_message_for_review
from discord_bot.verification.models import (
    SteamProfileCheckResult,
    VerificationAPIResult,
    VerificationRequest,
)
from discord_bot.verification.service import VerificationService
from discord_bot.verification.steam_client import (
    check_steam_profile_private,
    is_valid_steam_profile_url,
)

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


class IntakeContext(NamedTuple):
    """Live objects shared by every step of a DM intake."""

    cog: VerificationCog
    message: discord.Message
    guild: discord.Guild | None
    guild_name: str
    config: dict[str, Any]
    session: AsyncSession
    verification_service: VerificationService
    config_service: ConfigService


class IngestResult(NamedTuple):
    """Outcome of storing the items found in the DM."""

    request: VerificationRequest | None
    completed_screenshots: bool
    completed_steam: bool


def image_attachments_of(message: discord.Message) -> list[discord.Attachment]:
    """Return the image attachments of a message.

    Args:
        message (discord.Message): Received message.

    Returns:
        list[discord.Attachment]: Attachments whose content type is an image and
            whose size the verification API would accept.
    """
    images = [
        a for a in message.attachments if a.content_type and a.content_type.startswith("image/")
    ]
    # The size comes in the payload: dropping oversized screenshots here saves
    # storing a URL whose download the API call would reject afterwards anyway
    accepted = [a for a in images if a.size <= MAX_IMAGE_BYTES]
    if len(accepted) < len(images):
        logger.warning(
            f"Ignored {len(images) - len(accepted)} oversized screenshot(s) "
            f"from user {message.author.id}"
        )
    return accepted


def reminder_key(
    screenshots_saved: bool, steam_required: bool, steam_saved: bool
) -> ConfigKey | None:
    """Pick the reminder to send when the DM contained nothing new.

    Args:
        screenshots_saved (bool): Whether both screenshots are already stored.
        steam_required (bool): Whether a Steam profile URL is required.
        steam_saved (bool): Whether the Steam profile URL is already stored.

    Returns:
        ConfigKey | None: Message key, or None when nothing is outstanding.
    """
    if not screenshots_saved:
        return ConfigKey.WRONG_IMAGES_MESSAGE
    if steam_required and not steam_saved:
        return ConfigKey.STEAM_URL_RECEIVED_MESSAGE
    return None


def ack_key(completed_screenshots: bool) -> ConfigKey:
    """Pick the acknowledgment for a partial submission.

    Args:
        completed_screenshots (bool): Whether this DM completed the screenshots.

    Returns:
        ConfigKey: Message key.
    """
    if completed_screenshots:
        return ConfigKey.SCREENSHOTS_RECEIVED_AWAITING_STEAM_MESSAGE
    return ConfigKey.STEAM_URL_RECEIVED_MESSAGE


def requirements_met(request: VerificationRequest, steam_required: bool) -> bool:
    """Whether every required item is stored on the request.

    Args:
        request (VerificationRequest): Verification request.
        steam_required (bool): Whether a Steam profile URL is required.

    Returns:
        bool: True when both screenshots (and the Steam URL, if required) are present.
    """
    has_screenshots = bool(request.screenshot_1_url and request.screenshot_2_url)
    return has_screenshots and (not steam_required or bool(request.steam_profile_url))


async def _reply(ctx: IntakeContext, key: ConfigKey, **values: str | None) -> None:
    """Send a configured message to the user, with the username placeholder filled.

    Args:
        ctx (IntakeContext): Intake context.
        key (ConfigKey): Message key.
        **values (str | None): Extra placeholders.
    """
    formatted = format_message(
        template=ctx.config.get(key), username=ctx.message.author.name, **values
    )
    await ctx.message.channel.send(content=formatted)


async def _send_not_found(ctx: IntakeContext) -> None:
    """Tell the user the request no longer exists.

    Args:
        ctx (IntakeContext): Intake context.
    """
    await ctx.message.channel.send(content=ctx.config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE))


async def _store_screenshots(
    ctx: IntakeContext, request_id: int, attachments: list[discord.Attachment]
) -> VerificationRequest | None:
    """Validate and store the two screenshots.

    Args:
        ctx (IntakeContext): Intake context.
        request_id (int): Request ID.
        attachments (list[discord.Attachment]): Image attachments of the DM.

    Returns:
        VerificationRequest | None: Updated request, or None if the user was
            already told what went wrong.
    """
    if len(attachments) != 2:
        await _reply(ctx=ctx, key=ConfigKey.WRONG_IMAGES_MESSAGE)
        return None

    url1 = attachments[0].url
    url2 = attachments[1].url
    if not is_valid_discord_cdn_url(url1) or not is_valid_discord_cdn_url(url2):
        logger.warning(
            f"[{ctx.guild_name}] Invalid screenshot URLs for {ctx.message.author.name}: "
            f"{url1[:50]}..., {url2[:50]}..."
        )
        await _reply(ctx=ctx, key=ConfigKey.WRONG_IMAGES_MESSAGE)
        return None

    request = await ctx.verification_service.update_screenshots(
        request_id=request_id, url1=url1, url2=url2, guild_name=ctx.guild_name
    )
    if not request:
        await _send_not_found(ctx)
    return request


async def _store_steam_url(
    ctx: IntakeContext, request_id: int, url: str
) -> VerificationRequest | None:
    """Validate and store the Steam profile URL.

    Args:
        ctx (IntakeContext): Intake context.
        request_id (int): Request ID.
        url (str): Text sent by the user.

    Returns:
        VerificationRequest | None: Updated request, or None if the user was
            already told what went wrong.
    """
    if not is_valid_steam_profile_url(url):
        await _reply(ctx=ctx, key=ConfigKey.INVALID_STEAM_URL_MESSAGE)
        return None

    request = await ctx.verification_service.set_steam_profile_url(
        request_id=request_id, url=url, guild_name=ctx.guild_name
    )
    if not request:
        await _send_not_found(ctx)
    return request


async def _ingest_items(
    ctx: IntakeContext,
    request: VerificationRequest,
    attachments: list[discord.Attachment],
    message_text: str,
    steam_required: bool,
) -> IngestResult:
    """Store whatever new items the DM carries.

    Args:
        ctx (IntakeContext): Intake context.
        request (VerificationRequest): Current request.
        attachments (list[discord.Attachment]): Image attachments of the DM.
        message_text (str): Stripped text of the DM.
        steam_required (bool): Whether a Steam profile URL is required.

    Each item is handled independently: a rejected screenshot batch does not
    prevent a valid Steam URL sent in the same DM from being stored, and valid
    screenshots are kept (and acknowledged) even when the caption is not a
    valid Steam URL.

    Returns:
        IngestResult: Updated request (None when nothing left the request
            complete enough to continue) and which items this DM completed.
    """
    screenshots_saved = bool(request.screenshot_1_url and request.screenshot_2_url)
    steam_saved = bool(request.steam_profile_url)
    completed_screenshots = False
    completed_steam = False
    rejected = False  # the user was already told what was wrong

    updated = request
    if attachments and not screenshots_saved:
        stored = await _store_screenshots(ctx=ctx, request_id=request.id, attachments=attachments)
        if stored:
            updated = stored
            completed_screenshots = True
        else:
            rejected = True

    # After a rejection, plain captions are skipped so the user is not also
    # told the text was not a valid Steam URL
    try_steam = steam_required and not steam_saved and bool(message_text)
    if try_steam and rejected and not is_valid_steam_profile_url(message_text):
        try_steam = False
    if try_steam:
        stored = await _store_steam_url(ctx=ctx, request_id=request.id, url=message_text)
        if stored:
            updated = stored
            completed_steam = True
        else:
            rejected = True

    if not completed_screenshots and not completed_steam:
        if not rejected:
            # Nothing new was submitted; remind the user what is still outstanding
            key = reminder_key(
                screenshots_saved=screenshots_saved,
                steam_required=steam_required,
                steam_saved=steam_saved,
            )
            if key:
                await _reply(ctx=ctx, key=key)
        return IngestResult(request=None, completed_screenshots=False, completed_steam=False)

    return IngestResult(
        request=updated,
        completed_screenshots=completed_screenshots,
        completed_steam=completed_steam,
    )


async def _call_api(
    ctx: IntakeContext, request: VerificationRequest
) -> VerificationAPIResult | None:
    """Run the screenshots through the verification API, if configured.

    Args:
        ctx (IntakeContext): Intake context.
        request (VerificationRequest): Request with both screenshots stored.

    Returns:
        VerificationAPIResult | None: API result, or None when the API is not configured.
    """
    settings = ctx.cog.bot.settings.verification
    if not (settings.api_url and request.screenshot_1_url and request.screenshot_2_url):
        return None

    guild = ctx.guild
    api_result = await call_verification_api(
        url=settings.api_url,
        api_key=settings.api_key or None,
        image1_url=request.screenshot_1_url,
        image2_url=request.screenshot_2_url,
        timeout_seconds=settings.api_timeout,
        guild_name=guild.name if guild else "Unknown",
    )
    if not api_result.success:
        guild_prefix = f"[{guild.name}] " if guild else ""
        if api_result.status_code == 422:
            logger.info(
                f"{guild_prefix}Verification API returned invalid images: "
                f"{api_result.error_message}"
            )
        else:
            logger.warning(
                f"{guild_prefix}Verification API call failed: "
                f"status={api_result.status_code}, error={api_result.error_message}"
            )
    return api_result


async def _notify_mods(
    ctx: IntakeContext,
    request: VerificationRequest,
    api_result: VerificationAPIResult | None,
    steam_check: SteamProfileCheckResult | None,
) -> bool:
    """Update the moderation message with the results.

    Args:
        ctx (IntakeContext): Intake context.
        request (VerificationRequest): Request under review.
        api_result (VerificationAPIResult | None): Verification API result.
        steam_check (SteamProfileCheckResult | None): Steam privacy check result.

    Returns:
        bool: True if the request was auto-processed (approved/rejected).
    """
    guild = ctx.guild
    if not guild or not request.mod_message_id:
        return False
    mod_channel_id = ctx.config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return False
    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return False
    return await update_mod_message_for_review(
        cog=ctx.cog,
        channel=mod_channel,
        request=request,
        verification_service=ctx.verification_service,
        config=ctx.config,
        api_result=api_result,
        steam_check=steam_check,
    )


async def _refresh_tracker(ctx: IntakeContext, guild: discord.Guild) -> None:
    """Refresh the tracker message.

    Args:
        ctx (IntakeContext): Intake context.
        guild (discord.Guild): Discord guild.
    """
    await update_tracker_message(
        guild=guild,
        config=ctx.config,
        verification_service=ctx.verification_service,
        config_service=ctx.config_service,
    )


async def _complete_submission(
    ctx: IntakeContext, request: VerificationRequest, steam_required: bool
) -> None:
    """Every required item is present: move to review and notify moderators.

    Args:
        ctx (IntakeContext): Intake context.
        request (VerificationRequest): Complete request.
        steam_required (bool): Whether a Steam profile URL is required.
    """
    await ctx.verification_service.mark_pending_review(
        request_id=request.id, guild_name=ctx.guild_name
    )
    await _reply(
        ctx=ctx,
        key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE,
        server_name=ctx.guild_name if ctx.guild else "the server",
    )

    api_result = await _call_api(ctx=ctx, request=request)
    steam_check: SteamProfileCheckResult | None = None
    if steam_required and request.steam_profile_url:
        steam_check = await check_steam_profile_private(
            url=request.steam_profile_url, guild_name=ctx.guild_name
        )

    auto_processed = await _notify_mods(
        ctx=ctx, request=request, api_result=api_result, steam_check=steam_check
    )
    await ctx.session.commit()

    # Dropped only after the commit: a failure above rolls the request back to
    # awaiting screenshots, so the DM route and the screenshot timer must
    # survive for it to still complete or time out (the timeout handler takes
    # the same per-user lock and re-checks the status, so this cannot race it)
    cog = ctx.cog
    cog._pending_dm_verifications.pop(ctx.message.author.id, None)
    cog.cancel_screenshot_timer(request.id)
    if ctx.guild:
        await _refresh_tracker(ctx=ctx, guild=ctx.guild)
        if not auto_processed:
            await ctx.session.commit()


async def handle_dm_screenshots(
    cog: VerificationCog,
    message: discord.Message,
    guild_id: int,
    request_id: int,
) -> None:
    """Process DM message with screenshots and/or a Steam profile URL.

    Args:
        cog (VerificationCog): Cog instance.
        message (discord.Message): Received message.
        guild_id (int): Guild ID.
        request_id (int): Request ID.
    """
    attachments = image_attachments_of(message)
    message_text = (message.content or "").strip()
    guild = cog.bot.get_guild(guild_id)
    guild_name = guild.name if guild else f"Guild {guild_id}"

    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(guild_id=guild_id, config_service=config_service)
        verification_service = VerificationService(session=session)
        ctx = IntakeContext(
            cog=cog,
            message=message,
            guild=guild,
            guild_name=guild_name,
            config=config,
            session=session,
            verification_service=verification_service,
            config_service=config_service,
        )

        request = await verification_service.get_request(request_id)
        if not request:
            await _send_not_found(ctx)
            return

        steam_required = is_steam_profile_required(
            config=config, verification_type=VerificationType(request.verification_type)
        )
        ingest = await _ingest_items(
            ctx=ctx,
            request=request,
            attachments=attachments,
            message_text=message_text,
            steam_required=steam_required,
        )
        if not ingest.request:
            return

        if not requirements_met(request=ingest.request, steam_required=steam_required):
            await _reply(ctx=ctx, key=ack_key(completed_screenshots=ingest.completed_screenshots))
            await session.commit()
            return

        await _complete_submission(ctx=ctx, request=ingest.request, steam_required=steam_required)
