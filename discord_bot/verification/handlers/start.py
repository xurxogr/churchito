"""Verification start: create the request, DM the instructions, notify mods."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import discord

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import utc_timestamp
from discord_bot.verification.auto_processor import is_steam_profile_required
from discord_bot.verification.config import SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers.mod_messages import (
    build_initial_check_statuses,
    update_tracker_message,
)
from discord_bot.verification.handlers.utils import calculate_expires_timestamp
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


class StartContext(NamedTuple):
    """Live objects shared by the steps of a verification start."""

    cog: VerificationCog
    interaction: discord.Interaction
    guild: discord.Guild
    user: discord.User | discord.Member
    verification_type: VerificationType
    config: dict[str, Any]


def is_blocked_by_role(user: discord.User | discord.Member, blocking_roles: list[int]) -> bool:
    """Whether the user holds a role that blocks starting a verification.

    Args:
        user (discord.User | discord.Member): User starting verification.
        blocking_roles (list[int]): Configured blocking role IDs.

    Returns:
        bool: True if the user is a member with at least one blocking role.
    """
    if not blocking_roles or not isinstance(user, discord.Member):
        return False
    return bool({role.id for role in user.roles} & set(blocking_roles))


def effective_timeout_minutes(config: dict[str, Any]) -> int:
    """Screenshot timeout to apply, never zero.

    Without a deadline an abandoned verification would stay pending in the
    database forever, so non-positive values fall back to the default.

    Args:
        config (dict[str, Any]): Cog configuration.

    Returns:
        int: Timeout in minutes.
    """
    timeout_minutes = config.get(ConfigKey.SCREENSHOT_TIMEOUT_MINUTES) or 0
    if timeout_minutes <= 0:
        return SCREENSHOT_FALLBACK_TIMEOUT_MINUTES
    return timeout_minutes


def dm_template_key(verification_type: VerificationType) -> ConfigKey:
    """Config key of the DM instructions template for a verification type.

    Args:
        verification_type (VerificationType): Verification type.

    Returns:
        ConfigKey: Template key.
    """
    if verification_type == VerificationType.REGULAR:
        return ConfigKey.DM_INSTRUCTIONS_MESSAGE
    return ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE


async def _answer(ctx: StartContext, key: ConfigKey, fallback: str = "") -> None:
    """Answer the interaction with a configured ephemeral message.

    Args:
        ctx (StartContext): Start context.
        key (ConfigKey): Message key.
        fallback (str): Text used when the key is not configured.
    """
    await ctx.interaction.followup.send(ctx.config.get(key) or fallback, ephemeral=True)


async def _send_instructions(
    ctx: StartContext, request: VerificationRequest, timeout_minutes: int
) -> bool:
    """DM the verification instructions to the user.

    Args:
        ctx (StartContext): Start context.
        request (VerificationRequest): Newly created request.
        timeout_minutes (int): Screenshot timeout in minutes.

    Returns:
        bool: False if the user does not accept DMs.
    """
    config = ctx.config
    formatted_dm = format_message(
        template=config.get(dm_template_key(ctx.verification_type)),
        username=ctx.user.name,
        user_mention=ctx.user.mention,
        server_name=ctx.guild.name,
        verification_type=get_verification_type_display(
            verification_type=ctx.verification_type, config=config
        ),
        expires=calculate_expires_timestamp(
            created_at=request.created_at, timeout_minutes=timeout_minutes
        ),
        expected_faction=config.get(ConfigKey.VERIFICATION_FACTION) or "",
        expected_shard=config.get(ConfigKey.VERIFICATION_SHARD) or "",
    )
    try:
        await ctx.user.send(content=formatted_dm)
    except discord.Forbidden:
        return False
    except discord.HTTPException as e:
        # Any other delivery failure (e.g. a rendered template over the
        # 2000-character DM limit) must cancel the start the same way:
        # crashing here would roll the request back and leave the deferred
        # interaction unanswered
        logger.warning(f"[{ctx.guild.name}] Could not DM instructions to {ctx.user.name}: {e}")
        return False
    return True


async def _send_steam_request(ctx: StartContext) -> None:
    """DM the Steam profile request when the type requires it (best effort).

    Args:
        ctx (StartContext): Start context.
    """
    if not is_steam_profile_required(config=ctx.config, verification_type=ctx.verification_type):
        return
    formatted = format_message(
        template=ctx.config.get(ConfigKey.STEAM_PROFILE_REQUEST_MESSAGE),
        username=ctx.user.name,
        user_mention=ctx.user.mention,
        server_name=ctx.guild.name,
    )
    try:
        await ctx.user.send(content=formatted)
    except discord.HTTPException as e:
        # Best effort: the instructions DM already reached the user, so a
        # crash here would roll the request back and their screenshots would
        # arrive with no pending request to attach to
        logger.warning(f"[{ctx.guild.name}] Could not DM Steam request to {ctx.user.name}: {e}")


async def _post_mod_message(
    ctx: StartContext, mod_channel: discord.TextChannel, request: VerificationRequest
) -> discord.Message:
    """Send the initial moderation embeds for the request.

    Args:
        ctx (StartContext): Start context.
        mod_channel (discord.TextChannel): Moderation channel.
        request (VerificationRequest): Newly created request.

    Returns:
        discord.Message: The moderation message.
    """
    user = ctx.user
    member = user if isinstance(user, discord.Member) else None
    mod_embeds = create_mod_embeds(
        verification_type=ctx.verification_type,
        config=ctx.config,
        username=user.name,
        user_mention=user.mention,
        user_display_name=member.display_name if member else user.display_name,
        user_id=user.id,
        status=ctx.config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "",
        created_at=request.created_at.strftime("%Y-%m-%d %H:%M"),
        created_at_relative=f"<t:{utc_timestamp(request.created_at)}:R>",
        guild=ctx.guild,
        member=member,
        additional_sections=None,
        sections_context=None,
        api_status="",
        steam_profile_url="",
        **build_initial_check_statuses(),
    )
    return await mod_channel.send(embeds=mod_embeds)


async def _has_pending_request(ctx: StartContext, service: VerificationService) -> bool:
    """Refuse when the user already has a pending verification (here or elsewhere).

    Args:
        ctx (StartContext): Start context.
        service (VerificationService): Verification service.

    Returns:
        bool: True if the user was refused.
    """
    if await service.get_pending_by_user(guild_id=ctx.guild.id, user_id=ctx.user.id):
        await _answer(ctx=ctx, key=ConfigKey.ALREADY_PENDING_MESSAGE)
        return True
    if await service.get_any_pending_by_user(user_id=ctx.user.id):
        await _answer(
            ctx=ctx,
            key=ConfigKey.PENDING_IN_OTHER_SERVER_MESSAGE,
            fallback="You already have an ongoing verification in another server.",
        )
        return True
    return False


async def _create_and_notify(ctx: StartContext, mod_channel: discord.TextChannel) -> bool:
    """Create the request, DM the user, post the mod message and refresh the tracker.

    Args:
        ctx (StartContext): Start context.
        mod_channel (discord.TextChannel): Moderation channel.

    Returns:
        bool: True if the verification started (the user was already answered otherwise).
    """
    cog, guild, user = ctx.cog, ctx.guild, ctx.user
    async with cog.bot.database.session() as session:
        service = VerificationService(session=session)
        if await _has_pending_request(ctx=ctx, service=service):
            return False

        request = await service.create_request(
            guild_id=guild.id,
            user_id=user.id,
            username=user.name,
            guild_name=guild.name,
            verification_type=ctx.verification_type,
        )
        timeout_minutes = effective_timeout_minutes(ctx.config)

        if not await _send_instructions(ctx=ctx, request=request, timeout_minutes=timeout_minutes):
            await service.cancel(request_id=request.id, guild_name=guild.name)
            await session.commit()
            await _answer(ctx=ctx, key=ConfigKey.DM_DISABLED_MESSAGE)
            return False
        await _send_steam_request(ctx)

        try:
            mod_message = await _post_mod_message(ctx=ctx, mod_channel=mod_channel, request=request)
        except discord.HTTPException:
            # Without the mod message no moderator would ever see the request,
            # so it is cancelled instead of staying pending forever
            logger.warning(f"[{guild.name}] Could not post mod message in #{mod_channel.name}")
            await service.cancel(request_id=request.id, guild_name=guild.name)
            await session.commit()
            await _answer(ctx=ctx, key=ConfigKey.VERIFICATION_DISABLED_MESSAGE)
            return False
        await service.set_mod_message_id(request_id=request.id, message_id=mod_message.id)
        await session.commit()

        # Registered only after the commit: a failure above must not leave a
        # DM route or a screenshot timer pointing at a request that was never saved
        cog._pending_dm_verifications[user.id] = (guild.id, request.id)
        cog.start_screenshot_timer(
            request_id=request.id,
            guild_id=guild.id,
            user_id=user.id,
            timeout_minutes=timeout_minutes,
        )

        await update_tracker_message(
            guild=guild,
            config=ctx.config,
            verification_service=service,
            config_service=ConfigService(session=session),
        )
        await session.commit()
    return True


async def _handle_verification_start_locked(
    cog: VerificationCog,
    interaction: discord.Interaction,
    guild: discord.Guild,
    user: discord.User | discord.Member,
    verification_type: VerificationType,
) -> None:
    """Handle verification start (locked section).

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): User interaction.
        guild (discord.Guild): Guild where verification started.
        user (discord.User | discord.Member): User starting verification.
        verification_type (VerificationType): Verification type.
    """
    config = await cog._get_all_config(guild.id)
    ctx = StartContext(
        cog=cog,
        interaction=interaction,
        guild=guild,
        user=user,
        verification_type=verification_type,
        config=config,
    )

    if config.get(ConfigKey.VERIFICATION_ENABLED) is False:
        await _answer(ctx=ctx, key=ConfigKey.VERIFICATION_DISABLED_MESSAGE)
        return
    mod_channel = cog._get_mod_channel(guild=guild, config=config)
    if not mod_channel:
        await _answer(ctx=ctx, key=ConfigKey.VERIFICATION_DISABLED_MESSAGE)
        return
    if is_blocked_by_role(user=user, blocking_roles=config.get(ConfigKey.BLOCKING_ROLES) or []):
        await _answer(ctx=ctx, key=ConfigKey.ALREADY_VERIFIED_MESSAGE)
        return

    if await _create_and_notify(ctx=ctx, mod_channel=mod_channel):
        await _answer(ctx=ctx, key=ConfigKey.VERIFICATION_STARTED_MESSAGE)


async def handle_verification_start(
    cog: VerificationCog,
    interaction: discord.Interaction,
    verification_type: VerificationType,
) -> None:
    """Handle verification start when user clicks a button.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): User interaction.
        verification_type (VerificationType): Verification type.
    """
    if not interaction.guild or not interaction.user:
        return

    guild = interaction.guild
    user = interaction.user

    if not await cog._is_cog_enabled(guild.id):
        return

    await interaction.response.defer(ephemeral=True)

    # Acquire user lock to prevent race conditions from rapid clicks
    async with cog._user_locks.acquire(user.id):
        await _handle_verification_start_locked(
            cog=cog,
            interaction=interaction,
            guild=guild,
            user=user,
            verification_type=verification_type,
        )
