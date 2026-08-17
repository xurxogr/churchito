"""Moderation message update once screenshots arrive.

Decides between automatic processing (auto-approve / auto-reject) and manual
review, and refreshes the moderation embed accordingly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
from pydantic import BaseModel, ConfigDict

from discord_bot.verification.auto_processor import (
    get_auto_rejectable_failures,
    get_rejection_message,
    is_auto_reject_enabled,
    is_steam_profile_required,
    process_verification,
)
from discord_bot.verification.enums import (
    AutoProcessMode,
    ConfigKey,
    NameMatchMode,
    RejectType,
    VerificationType,
)
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers.auto_processing import (
    handle_auto_rejection,
    process_auto_verification,
    send_mod_ping_message,
)
from discord_bot.verification.handlers.mod_messages import (
    STATUS_DISABLED,
    STATUS_FAILED,
    STATUS_PASSED,
)
from discord_bot.verification.handlers.utils import (
    create_screenshot_embeds,
    get_api_error_message,
    get_embed_additional_sections,
    get_ready_for_approval_status,
)
from discord_bot.verification.models import (
    SteamProfileCheckResult,
    VerificationAPIResponse,
    VerificationAPIResult,
    VerificationRequest,
)
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import ModReviewView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)

_NOT_AVAILABLE = "N/A"
_HTTP_UNPROCESSABLE = 422


class ApiOutcome(BaseModel):
    """What the verification API call contributed to the review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    player_info: dict[str, Any] | None = None
    api_status: str = ""


class AutoDecision(BaseModel):
    """Result of the automatic processing attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    processed: bool
    failures: set[RejectType]
    status_text: str | None = None


class ReviewContext(NamedTuple):
    """Handles shared by every branch of the review update.

    Kept as a NamedTuple rather than a Pydantic model: it only bundles live
    Discord/service objects that must be passed through untouched.
    """

    cog: VerificationCog
    guild: discord.Guild
    request: VerificationRequest
    verification_service: VerificationService
    config: dict[str, Any]
    mod_message: discord.Message
    embeds: list[discord.Embed]
    additional_sections: list[dict[str, Any]]
    sections_context: dict[str, Any] | None
    api_status: str


def _check_status(enabled: bool, failed: bool) -> str:
    """Pick the indicator for one check.

    Args:
        enabled (bool): Whether the check ran and is configured.
        failed (bool): Whether the check failed.

    Returns:
        str: Disabled, failed or passed indicator.
    """
    if not enabled:
        return STATUS_DISABLED
    return STATUS_FAILED if failed else STATUS_PASSED


def _name_check_enabled(config: dict[str, Any]) -> bool:
    """Whether the name-match check is configured (legacy booleans supported).

    Args:
        config (dict[str, Any]): Cog configuration.

    Returns:
        bool: True when name matching is enabled.
    """
    match_mode = config.get(ConfigKey.VERIFICATION_MATCH_NAME, NameMatchMode.NONE)
    if match_mode is True:
        return True
    if match_mode is False or not match_mode:
        return False
    return bool(match_mode != NameMatchMode.NONE)


def build_check_statuses(
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
        api_response_exists (bool): Whether an API response exists (checks ran).

    Returns:
        dict[str, str]: Status placeholders (faction_status, shard_status, etc.)
    """
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    steam_required = is_steam_profile_required(
        config=config, verification_type=VerificationType(request.verification_type)
    )
    return {
        "faction_status": _check_status(
            enabled=api_response_exists and bool(config.get(ConfigKey.VERIFICATION_FACTION)),
            failed=RejectType.WRONG_FACTION in failures,
        ),
        "shard_status": _check_status(
            enabled=api_response_exists and bool(config.get(ConfigKey.VERIFICATION_SHARD)),
            failed=RejectType.WRONG_SHARD in failures,
        ),
        "regiment_status": _check_status(
            enabled=api_response_exists and request.verification_type == VerificationType.REGULAR,
            failed=RejectType.HAS_REGIMENT in failures,
        ),
        "name_status": _check_status(
            enabled=api_response_exists and _name_check_enabled(config),
            failed=RejectType.NAME_MISMATCH in failures,
        ),
        "time_status": _check_status(
            enabled=api_response_exists and bool(time_diff_limit and time_diff_limit > 0),
            failed=RejectType.TIME_DIFF in failures,
        ),
        "steam_status": _check_status(
            enabled=steam_required, failed=RejectType.STEAM_PRIVATE in failures
        ),
    }


def build_rejection_messages(config: dict[str, Any], failures: set[RejectType]) -> list[str]:
    """Build rejection messages for all failures, in enum order.

    Args:
        config (dict[str, Any]): Cog configuration.
        failures (set[RejectType]): Set of failure types.

    Returns:
        list[str]: Formatted rejection messages.
    """
    placeholders: dict[RejectType, dict[str, Any]] = {
        RejectType.WRONG_SHARD: {"shard": config.get(ConfigKey.VERIFICATION_SHARD, "")},
        RejectType.WRONG_FACTION: {"faction": config.get(ConfigKey.VERIFICATION_FACTION, "")},
    }
    return [
        get_rejection_message(
            config=config, reason=reject_type, **placeholders.get(reject_type, {})
        )
        for reject_type in RejectType
        if reject_type in failures
    ]


def _player_info(response: VerificationAPIResponse) -> dict[str, Any]:
    """Map the API response to the player-info placeholders.

    Args:
        response (VerificationAPIResponse): Successful API response.

    Returns:
        dict[str, Any]: Placeholder values with N/A fallbacks.
    """
    return {
        "name": response.name or _NOT_AVAILABLE,
        "regiment": response.regiment or _NOT_AVAILABLE,
        "level": str(response.level),
        "faction": response.faction or _NOT_AVAILABLE,
        "shard": response.shard or _NOT_AVAILABLE,
        "time": response.ingame_time or _NOT_AVAILABLE,
        "war": str(response.war_number),
        "war_time": response.current_ingame_time or _NOT_AVAILABLE,
    }


def summarize_api_result(
    api_result: VerificationAPIResult | None, config: dict[str, Any]
) -> ApiOutcome:
    """Derive player info and the API status placeholder from the API result.

    Args:
        api_result (VerificationAPIResult | None): Verification API result.
        config (dict[str, Any]): Cog configuration.

    Returns:
        ApiOutcome: Player info (when the call succeeded) and status text otherwise.
    """
    if not api_result:
        return ApiOutcome()
    if api_result.success and api_result.response:
        return ApiOutcome(player_info=_player_info(api_result.response))
    if api_result.status_code == _HTTP_UNPROCESSABLE:
        reject_msg = config.get(ConfigKey.REJECT_WRONG_CAPTURES) or "Invalid captures"
        return ApiOutcome(api_status=f"⚠️ **{reject_msg}**")
    error_msg = get_api_error_message(api_result.status_code)
    return ApiOutcome(api_status=f"❌ **API Error:** {error_msg}")


def initial_failures(steam_check: SteamProfileCheckResult | None) -> set[RejectType]:
    """Seed the failure set from the Steam privacy check.

    Args:
        steam_check (SteamProfileCheckResult | None): Steam profile privacy check result.

    Returns:
        set[RejectType]: ``{STEAM_PRIVATE}`` for a confirmed private profile, else empty.
    """
    if steam_check and steam_check.success and steam_check.is_private:
        return {RejectType.STEAM_PRIVATE}
    return set()


def resolve_auto_flags(
    config: dict[str, Any], guild_name: str, steam_check_inconclusive: bool
) -> tuple[bool, bool]:
    """Resolve the auto-process mode into (auto_reject, auto_approve).

    Legacy boolean values map to BOTH / NONE. An inconclusive Steam check never
    auto-approves on an unverified assumption of "public".

    Args:
        config (dict[str, Any]): Cog configuration.
        guild_name (str): Guild name for logging.
        steam_check_inconclusive (bool): Whether the Steam check could not complete.

    Returns:
        tuple[bool, bool]: ``(auto_reject, auto_approve)``
    """
    auto_mode = config.get(ConfigKey.VERIFICATION_AUTOMATIC, AutoProcessMode.NONE)
    logger.debug(f"[{guild_name}] Auto mode: {auto_mode!r} (type={type(auto_mode).__name__})")
    if auto_mode is True:
        auto_mode = AutoProcessMode.BOTH
    elif auto_mode is False or not auto_mode:
        auto_mode = AutoProcessMode.NONE

    auto_reject = auto_mode in (AutoProcessMode.REJECT_ONLY, AutoProcessMode.BOTH)
    auto_approve = (
        auto_mode in (AutoProcessMode.APPROVE_ONLY, AutoProcessMode.BOTH)
        and not steam_check_inconclusive
    )
    logger.debug(f"[{guild_name}] auto_reject={auto_reject}, auto_approve={auto_approve}")
    return auto_reject, auto_approve


async def _auto_reject(ctx: ReviewContext, reason: str, check_statuses: dict[str, str]) -> None:
    """Auto-reject the request and refresh the moderation message.

    Args:
        ctx (ReviewContext): Shared review handles.
        reason (str): Rejection reason shown to the user and moderators.
        check_statuses (dict[str, str]): Status placeholders for the embed.
    """
    await handle_auto_rejection(
        cog=ctx.cog,
        guild=ctx.guild,
        request=ctx.request,
        verification_service=ctx.verification_service,
        config=ctx.config,
        mod_message=ctx.mod_message,
        embeds=ctx.embeds,
        reason=reason,
        additional_sections=ctx.additional_sections,
        sections_context=ctx.sections_context,
        check_statuses=check_statuses,
        api_status=ctx.api_status,
    )


async def _try_reject_without_api(ctx: ReviewContext, failures: set[RejectType]) -> bool:
    """Auto-reject on Steam-only failures when no API result is available.

    Args:
        ctx (ReviewContext): Shared review handles.
        failures (set[RejectType]): Failures known so far (Steam check).

    Returns:
        bool: True when the request was auto-rejected.
    """
    auto_rejectable = get_auto_rejectable_failures(config=ctx.config, failures=failures)
    if not auto_rejectable:
        return False
    await _auto_reject(
        ctx=ctx,
        reason="\n".join(build_rejection_messages(config=ctx.config, failures=auto_rejectable)),
        check_statuses=build_check_statuses(
            config=ctx.config, failures=failures, request=ctx.request, api_response_exists=False
        ),
    )
    return True


async def _try_reject_invalid_screenshots(ctx: ReviewContext) -> bool:
    """Auto-reject unreadable screenshots (API 422) when enabled.

    Args:
        ctx (ReviewContext): Shared review handles.

    Returns:
        bool: True when the request was auto-rejected.
    """
    if not is_auto_reject_enabled(config=ctx.config, reason=RejectType.INVALID_SCREENSHOTS):
        return False
    await _auto_reject(
        ctx=ctx,
        reason=get_rejection_message(config=ctx.config, reason=RejectType.INVALID_SCREENSHOTS),
        # No valid response, so the other checks didn't run
        check_statuses=build_check_statuses(
            config=ctx.config,
            failures={RejectType.INVALID_SCREENSHOTS},
            request=ctx.request,
            api_response_exists=False,
        ),
    )
    return True


async def _process_api_response(
    ctx: ReviewContext,
    api_response: VerificationAPIResponse,
    failures: set[RejectType],
    auto_reject: bool,
    auto_approve: bool,
) -> AutoDecision:
    """Run the verification checks and auto-approve/reject when the rules allow it.

    Args:
        ctx (ReviewContext): Shared review handles.
        api_response (VerificationAPIResponse): Successful API response.
        failures (set[RejectType]): Failures known before the checks (Steam).
        auto_reject (bool): Whether auto-rejection is enabled.
        auto_approve (bool): Whether auto-approval is enabled.

    Returns:
        AutoDecision: Whether it was processed, the full failure set and an optional
            status override for manual review.
    """
    member = ctx.guild.get_member(ctx.request.user_id)
    all_failures = failures | process_verification(
        request=ctx.request,
        api_response=api_response,
        config=ctx.config,
        member_display_name=member.display_name if member else ctx.request.username,
    )
    should_approve = not all_failures
    logger.debug(
        f"[{ctx.guild.name}] Verification result: failures={all_failures}, "
        f"should_approve={should_approve}, auto_reject={auto_reject}"
    )

    # Auto-reject only if at least one failure has auto-reject enabled
    auto_rejectable: set[RejectType] = set()
    should_auto_reject = auto_reject
    if all_failures and auto_reject:
        auto_rejectable = get_auto_rejectable_failures(config=ctx.config, failures=all_failures)
        should_auto_reject = bool(auto_rejectable)
        logger.debug(
            f"[{ctx.guild.name}] Auto-reject check: auto_rejectable={auto_rejectable}, "
            f"should_auto_reject={should_auto_reject}"
        )

    rejection_reason: str | None = None
    if all_failures:
        failures_for_message = auto_rejectable if should_auto_reject else all_failures
        rejection_reason = "\n".join(
            build_rejection_messages(config=ctx.config, failures=failures_for_message)
        )

    processed = await process_auto_verification(
        cog=ctx.cog,
        guild=ctx.guild,
        request=ctx.request,
        verification_service=ctx.verification_service,
        config=ctx.config,
        mod_message=ctx.mod_message,
        embeds=ctx.embeds,
        should_approve=should_approve,
        rejection_reason=rejection_reason,
        auto_approve=auto_approve,
        auto_reject=should_auto_reject,
        additional_sections=ctx.additional_sections,
        sections_context=ctx.sections_context,
        check_statuses=build_check_statuses(
            config=ctx.config, failures=all_failures, request=ctx.request, api_response_exists=True
        ),
        api_status=ctx.api_status,
    )
    status_text = None
    if not processed and should_approve and not auto_approve:
        status_text = get_ready_for_approval_status(config=ctx.config, guild=ctx.guild)
    return AutoDecision(processed=processed, failures=all_failures, status_text=status_text)


async def _try_auto_process(
    ctx: ReviewContext,
    api_result: VerificationAPIResult | None,
    failures: set[RejectType],
    auto_reject: bool,
    auto_approve: bool,
) -> AutoDecision:
    """Attempt automatic processing in order: Steam-only, invalid screenshots, API checks.

    Args:
        ctx (ReviewContext): Shared review handles.
        api_result (VerificationAPIResult | None): Verification API result.
        failures (set[RejectType]): Failures known so far (Steam check).
        auto_reject (bool): Whether auto-rejection is enabled.
        auto_approve (bool): Whether auto-approval is enabled.

    Returns:
        AutoDecision: Outcome; ``processed`` is False when manual review is needed.
    """
    if not api_result and failures and auto_reject:
        if await _try_reject_without_api(ctx=ctx, failures=failures):
            return AutoDecision(processed=True, failures=failures)

    if api_result and api_result.status_code == _HTTP_UNPROCESSABLE and auto_reject:
        if await _try_reject_invalid_screenshots(ctx=ctx):
            return AutoDecision(processed=True, failures=failures)

    if api_result and api_result.success and api_result.response:
        return await _process_api_response(
            ctx=ctx,
            api_response=api_result.response,
            failures=failures,
            auto_reject=auto_reject,
            auto_approve=auto_approve,
        )
    return AutoDecision(processed=False, failures=failures)


async def _show_manual_review(
    ctx: ReviewContext,
    channel: discord.TextChannel,
    failures: set[RejectType],
    api_response_exists: bool,
    status_text: str,
) -> None:
    """Refresh the moderation message with accept/reject buttons and ping moderators.

    Args:
        ctx (ReviewContext): Shared review handles.
        channel (discord.TextChannel): Moderation channel.
        failures (set[RejectType]): Failures to reflect in the check statuses.
        api_response_exists (bool): Whether the API checks ran.
        status_text (str): Status line for the embed.
    """
    request = ctx.request
    verification_type = VerificationType(request.verification_type)
    type_display = get_verification_type_display(
        verification_type=verification_type, config=ctx.config
    )
    view = ModReviewView(
        public_id=request.public_id,
        accept_label=format_message(
            template=ctx.config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Accept",
            verification_type=type_display,
        ),
        reject_label=ctx.config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Reject",
    )
    member = ctx.guild.get_member(request.user_id)
    main_embeds = create_mod_embeds(
        verification_type=verification_type,
        config=ctx.config,
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        user_display_name=member.display_name if member else request.username,
        user_id=request.user_id,
        status=status_text,
        created_at=request.created_at.strftime("%Y-%m-%d %H:%M"),
        created_at_relative=f"<t:{int(request.created_at.timestamp())}:R>",
        guild=ctx.guild,
        member=member,
        additional_sections=ctx.additional_sections,
        sections_context=ctx.sections_context,
        api_status=ctx.api_status,
        steam_profile_url=request.steam_profile_url or "",
        **build_check_statuses(
            config=ctx.config,
            failures=failures,
            request=request,
            api_response_exists=api_response_exists,
        ),
    )
    await ctx.mod_message.edit(embeds=[*main_embeds, *ctx.embeds], view=view)
    await send_mod_ping_message(channel=channel, config=ctx.config)


async def update_mod_message_for_review(
    cog: VerificationCog,
    channel: discord.TextChannel,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    api_result: VerificationAPIResult | None = None,
    steam_check: SteamProfileCheckResult | None = None,
) -> bool:
    """Update moderation message when screenshots are received.

    Args:
        cog (VerificationCog): Cog instance.
        channel (discord.TextChannel): Moderation channel.
        request (VerificationRequest): Verification request.
        verification_service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        api_result (VerificationAPIResult | None): Verification API result.
        steam_check (SteamProfileCheckResult | None): Steam profile privacy check result.

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

    outcome = summarize_api_result(api_result=api_result, config=config)
    if outcome.player_info is not None:
        await verification_service.set_player_info(
            request_id=request.id, player_info=outcome.player_info
        )
    additional_sections, sections_context = await get_embed_additional_sections(
        request=request,
        config=config,
        verification_service=verification_service,
        player_info=outcome.player_info,
    )
    embeds = create_screenshot_embeds(url1=request.screenshot_1_url, url2=request.screenshot_2_url)
    ctx = ReviewContext(
        cog=cog,
        guild=channel.guild,
        request=request,
        verification_service=verification_service,
        config=config,
        mod_message=mod_message,
        embeds=embeds,
        additional_sections=additional_sections,
        sections_context=sections_context,
        api_status=outcome.api_status,
    )

    failures = initial_failures(steam_check=steam_check)
    auto_reject, auto_approve = resolve_auto_flags(
        config=config,
        guild_name=channel.guild.name,
        steam_check_inconclusive=bool(steam_check and not steam_check.success),
    )
    status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
    if (auto_reject or auto_approve) and (api_result or failures):
        decision = await _try_auto_process(
            ctx=ctx,
            api_result=api_result,
            failures=failures,
            auto_reject=auto_reject,
            auto_approve=auto_approve,
        )
        if decision.processed:
            return True
        failures = decision.failures
        if decision.status_text is not None:
            status_text = decision.status_text

    await _show_manual_review(
        ctx=ctx,
        channel=channel,
        failures=failures,
        api_response_exists=outcome.player_info is not None,
        status_text=status_text,
    )
    return False
