"""Moderator actions: accept, reject and review."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import has_any_role
from discord_bot.verification.enums import (
    ConfigKey,
    VerificationStatus,
    VerificationType,
)
from discord_bot.verification.formatters import (
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers.mod_messages import (
    update_mod_message_for_manual_review,
    update_mod_message_status,
    update_tracker_message,
)
from discord_bot.verification.handlers.utils import get_ready_for_approval_status
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import RejectionReasonView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


class ModActionContext(NamedTuple):
    """Validated context for moderation actions."""

    config: dict[str, Any]
    request: VerificationRequest
    service: VerificationService


async def authorize_and_defer(
    cog: VerificationCog,
    interaction: discord.Interaction,
    permission_error_key: ConfigKey,
    permission_error_default: str,
    ephemeral: bool = False,
) -> bool:
    """Check moderator permission and acknowledge the click before any waiting.

    Discord expires an unacknowledged interaction after a few seconds, so the
    defer must happen BEFORE waiting on the per-request lock: a moderator
    clicking while another decision is still in flight would otherwise see
    "interaction failed" instead of the "already processed" notice.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        permission_error_key (ConfigKey): Permission error message key.
        permission_error_default (str): Default message if not configured.
        ephemeral (bool): Whether the deferred response is ephemeral.

    Returns:
        bool: True when the moderator may proceed and the click was acknowledged.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(
            guild_id=interaction.guild.id, config_service=config_service
        )

    if not has_any_role(member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []):
        await interaction.response.send_message(
            content=config.get(permission_error_key) or permission_error_default,
            ephemeral=True,
        )
        return False

    try:
        await interaction.response.defer(ephemeral=ephemeral)
    except discord.HTTPException as e:
        logger.warning(f"[{interaction.guild.name}] Mod action click expired before defer: {e}")
        return False
    return True


async def validate_mod_action(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
    session: AsyncSession,
) -> ModActionContext | None:
    """Validate and prepare context for moderation actions.

    The caller must have passed ``authorize_and_defer`` first: permission is
    already checked and the interaction deferred. This performs the
    validations that need the per-request lock:
    - Get the request
    - Verify it exists and is pending review

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
        session (AsyncSession): Database session.

    Returns:
        ModActionContext | None: Validated context or None if any validation failed.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None

    config_service = ConfigService(session=session)
    config = await cog._get_all_config(guild_id=interaction.guild.id, config_service=config_service)

    verification_service = VerificationService(session=session)
    request = await verification_service.get_by_public_id(public_id=public_id)

    if not request or request.guild_id != interaction.guild.id:
        await interaction.followup.send(
            content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Request not found.",
            ephemeral=True,
        )
        return None

    if request.status != VerificationStatus.PENDING_REVIEW:
        await interaction.followup.send(
            content=config.get(ConfigKey.REQUEST_ALREADY_PROCESSED_MESSAGE)
            or "This request has already been processed.",
            ephemeral=True,
        )
        return None

    return ModActionContext(config=config, request=request, service=verification_service)


class RoleChanges(NamedTuple):
    """Roles to grant/revoke on approval and the approval DM template key."""

    add: list[int]
    remove: list[int]
    message_key: ConfigKey


def previous_statuses(
    config: dict[str, Any], guild: discord.Guild, request: VerificationRequest
) -> list[str]:
    """Status texts the mod message may show right before a moderator decision.

    The message can be at "pending review", "ready for approval" (OCR passed) or
    still at the auto-rejected status when a review did not update it.

    Args:
        config (dict[str, Any]): Cog configuration.
        guild (discord.Guild): Guild of the request.
        request (VerificationRequest): Request being decided.

    Returns:
        list[str]: Ready-for-approval, pending-review and auto-rejected texts.
    """
    pending_review = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
    ready_for_approval = get_ready_for_approval_status(config=config, guild=guild)
    auto_rejected = format_message(
        template=config.get(ConfigKey.STATUS_REJECTED),
        moderator="Auto",
        moderator_display_name="Auto",
        reason=request.rejection_reason or "",
    )
    return [ready_for_approval, pending_review, auto_rejected]


def approval_role_changes(config: dict[str, Any], verification_type: str) -> RoleChanges:
    """Role changes and DM template that apply when a verification is approved.

    Args:
        config (dict[str, Any]): Cog configuration.
        verification_type (str): Verification type of the request.

    Returns:
        RoleChanges: Roles to add/remove and the approval message key.
    """
    if verification_type == VerificationType.REGULAR:
        return RoleChanges(
            add=config.get(ConfigKey.REGULAR_ROLES_ADD) or [],
            remove=config.get(ConfigKey.REGULAR_ROLES_REMOVE) or [],
            message_key=ConfigKey.APPROVAL_MESSAGE_REGULAR,
        )
    return RoleChanges(
        add=config.get(ConfigKey.ALLY_ROLES_ADD) or [],
        remove=config.get(ConfigKey.ALLY_ROLES_REMOVE) or [],
        message_key=ConfigKey.APPROVAL_MESSAGE_ALLY,
    )


def approval_confirmation(confirmation: str, failed_roles: list[str]) -> str:
    """Moderator confirmation, with a warning when some roles could not be changed.

    Args:
        confirmation (str): Formatted confirmation text.
        failed_roles (list[str]): Failed role changes as "@Role (add|remove)".

    Returns:
        str: Text to send to the moderator.
    """
    if not failed_roles:
        return confirmation
    return (
        f"{confirmation}\n\n"
        f"⚠️ **Warning:** Could not modify some roles: {', '.join(failed_roles)}\n"
        f"Verify that:\n"
        f"• The bot has the **Manage Roles** permission\n"
        f"• The bot's role is **above** these roles in the hierarchy"
    )


async def _change_role(
    member: discord.Member, role: discord.Role, action: Literal["add", "remove"]
) -> bool:
    """Add or remove a single role, reporting permission failures.

    Args:
        member (discord.Member): Member to change.
        role (discord.Role): Role to add or remove.
        action (Literal["add", "remove"]): Whether to add or remove the role.

    Returns:
        bool: True if the change was applied.
    """
    try:
        if action == "add":
            await member.add_roles(role)
        else:
            await member.remove_roles(role)
    except discord.Forbidden as e:
        logger.warning(
            f"Could not {action} role {role.name} ({role.id}): {e}. "
            f"Verify the bot has 'Manage Roles' permission and that "
            f"its role is above @{role.name} in the hierarchy."
        )
        return False
    return True


async def apply_role_changes(
    guild: discord.Guild, member: discord.Member, changes: RoleChanges
) -> list[str]:
    """Grant and revoke the configured roles on an approved member.

    Missing roles are skipped; forbidden changes are collected for the moderator.

    Args:
        guild (discord.Guild): Guild of the member.
        member (discord.Member): Approved member.
        changes (RoleChanges): Roles to add and remove.

    Returns:
        list[str]: Failed changes as "@Role (add|remove)".
    """
    failed: list[str] = []
    steps: list[tuple[Literal["add", "remove"], list[int]]] = [
        ("add", changes.add),
        ("remove", changes.remove),
    ]
    for action, role_ids in steps:
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if not role:
                logger.warning(f"[{guild.name}] Role not found (ID: {role_id})")
                continue
            if not await _change_role(member=member, role=role, action=action):
                failed.append(f"@{role.name} ({action})")
    return failed


async def _dm_member(member: discord.Member, content: str) -> None:
    """DM the member, ignoring closed DMs.

    Args:
        member (discord.Member): Member to notify.
        content (str): Message text.
    """
    try:
        await member.send(content=content)
    except discord.Forbidden:
        pass


async def _grant_approval(
    guild: discord.Guild, config: dict[str, Any], request: VerificationRequest
) -> list[str]:
    """Apply the approval roles and DM the user, if still in the guild.

    Args:
        guild (discord.Guild): Guild of the request.
        config (dict[str, Any]): Cog configuration.
        request (VerificationRequest): Approved request.

    Returns:
        list[str]: Failed role changes as "@Role (add|remove)".
    """
    member = guild.get_member(request.user_id)
    if not member:
        return []
    changes = approval_role_changes(config=config, verification_type=request.verification_type)
    failed_roles = await apply_role_changes(guild=guild, member=member, changes=changes)
    await _dm_member(
        member=member,
        content=format_message(
            template=config.get(changes.message_key),
            username=request.username,
            server_name=guild.name,
        ),
    )
    return failed_roles


async def _notify_rejection(
    guild: discord.Guild, config: dict[str, Any], request: VerificationRequest, reason: str
) -> None:
    """DM the rejection reason to the user, if still in the guild.

    Args:
        guild (discord.Guild): Guild of the request.
        config (dict[str, Any]): Cog configuration.
        request (VerificationRequest): Rejected request.
        reason (str): Rejection reason.
    """
    member = guild.get_member(request.user_id)
    if not member:
        return
    type_display = get_verification_type_display(
        verification_type=VerificationType(request.verification_type), config=config
    )
    await _dm_member(
        member=member,
        content=format_message(
            template=config.get(ConfigKey.REJECTION_MESSAGE),
            username=request.username,
            server_name=guild.name,
            verification_type=type_display,
            reason=reason,
        ),
    )


async def _publish_decision(
    session: AsyncSession,
    guild: discord.Guild,
    ctx: ModActionContext,
    moderator: discord.Member,
    status_key: ConfigKey,
    color: discord.Color,
    previous: list[str],
    **status_values: str,
) -> None:
    """Update the mod message with the decision, commit and refresh the tracker.

    Args:
        session (AsyncSession): Database session.
        guild (discord.Guild): Guild of the request.
        ctx (ModActionContext): Validated action context.
        moderator (discord.Member): Moderator who decided.
        status_key (ConfigKey): Template key of the new status text.
        color (discord.Color): Embed color for the decision.
        previous (list[str]): Status texts the message may currently show.
        **status_values (str): Extra placeholders for the status template.
    """
    status = format_message(
        template=ctx.config.get(status_key),
        moderator=moderator.name,
        moderator_display_name=moderator.display_name,
        **status_values,
    )
    await update_mod_message_status(
        guild=guild,
        request=ctx.request,
        config=ctx.config,
        status=status,
        color=color,
        previous_statuses=previous,
    )
    await session.commit()

    await update_tracker_message(
        guild=guild,
        config=ctx.config,
        verification_service=ctx.service,
        config_service=ConfigService(session=session),
    )
    await session.commit()


async def handle_accept(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
) -> None:
    """Handle verification approval.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    if not await authorize_and_defer(
        cog=cog,
        interaction=interaction,
        permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
        permission_error_default="You do not have permission to approve verifications.",
    ):
        return

    # Serialize decisions per request: validate_mod_action checks the status
    # before the decision commits, so two overlapping moderators would both
    # pass it and both apply their decision (roles, DMs, mod message)
    async with (
        cog._request_locks.acquire(public_id),
        cog.bot.database.session() as session,
    ):
        ctx = await validate_mod_action(
            cog=cog, interaction=interaction, public_id=public_id, session=session
        )
        if not ctx:
            return

        config, request, verification_service = ctx
        # Captured before approving: the mod message may still show any of these
        previous = previous_statuses(config=config, guild=interaction.guild, request=request)

        await verification_service.approve(
            request_id=request.id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
            guild_name=interaction.guild.name,
        )
        failed_roles = await _grant_approval(
            guild=interaction.guild, config=config, request=request
        )

        await _publish_decision(
            session=session,
            guild=interaction.guild,
            ctx=ctx,
            moderator=interaction.user,
            status_key=ConfigKey.STATUS_APPROVED,
            color=discord.Color.green(),
            previous=previous,
        )

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_APPROVED_CONFIRMATION)
            or "Verification approved for {username}.",
            username=request.username,
        )
        await interaction.followup.send(
            content=approval_confirmation(confirmation=confirmation, failed_roles=failed_roles),
            ephemeral=True,
        )


REJECTION_REASON_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey.REJECT_WRONG_CAPTURES,
    ConfigKey.REJECT_NAME_MISMATCH,
    ConfigKey.REJECT_HAS_REGIMENT,
    ConfigKey.REJECT_TIME_DIFF,
    ConfigKey.REJECT_WRONG_SHARD,
    ConfigKey.REJECT_WRONG_FACTION,
    ConfigKey.REJECT_STEAM_PRIVATE,
)


def _rejection_reason(config: dict[str, Any], key: ConfigKey) -> str | None:
    """Configured rejection reason for a key, with shard/faction filled in.

    Args:
        config (dict[str, Any]): Cog configuration.
        key (ConfigKey): Rejection reason key.

    Returns:
        str | None: The reason, or None when unset or missing its expected value.
    """
    reason = config.get(key) or ""
    if not reason.strip():
        return None
    if key == ConfigKey.REJECT_WRONG_SHARD:
        expected_shard = config.get(ConfigKey.VERIFICATION_SHARD) or ""
        return reason.replace("{shard}", expected_shard) if expected_shard else None
    if key == ConfigKey.REJECT_WRONG_FACTION:
        expected_faction = config.get(ConfigKey.VERIFICATION_FACTION) or ""
        return reason.replace("{faction}", expected_faction) if expected_faction else None
    return reason


def build_rejection_reasons(config: dict[str, Any]) -> list[str]:
    """Rejection reasons offered in the selector, in canonical order.

    Args:
        config (dict[str, Any]): Cog configuration.

    Returns:
        list[str]: Non-empty reasons; shard/faction ones only when configured.
    """
    reasons = (_rejection_reason(config=config, key=key) for key in REJECTION_REASON_KEYS)
    return [reason for reason in reasons if reason is not None]


def build_rejection_view(public_id: str, config: dict[str, Any]) -> RejectionReasonView:
    """Rejection reason selector with all configurable texts resolved.

    Args:
        public_id (str): Public request ID (NanoID).
        config (dict[str, Any]): Cog configuration.

    Returns:
        RejectionReasonView: The selector view.
    """
    return RejectionReasonView(
        public_id=public_id,
        reasons=build_rejection_reasons(config),
        other_label=config.get(ConfigKey.REJECTION_OTHER_LABEL) or "Other reason...",
        other_description=config.get(ConfigKey.REJECTION_OTHER_DESCRIPTION)
        or "Write a custom reason",
        placeholder=config.get(ConfigKey.REJECTION_SELECT_PLACEHOLDER)
        or "Select the rejection reason...",
        modal_title=config.get(ConfigKey.REJECTION_MODAL_TITLE) or "Rejection Reason",
        modal_label=config.get(ConfigKey.REJECTION_MODAL_LABEL) or "Reason",
        modal_placeholder=config.get(ConfigKey.REJECTION_MODAL_PLACEHOLDER)
        or "Explain why the verification is being rejected...",
    )


async def show_rejection_select(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
) -> None:
    """Show rejection reason selector.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    guild_id = interaction.guild.id

    if not await cog._is_cog_enabled(guild_id):
        return

    config = await cog._get_all_config(guild_id)

    if not has_any_role(member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []):
        await interaction.response.send_message(
            content="You do not have permission to reject verifications.",
            ephemeral=True,
        )
        return

    async with cog.bot.database.session() as session:
        verification_service = VerificationService(session=session)
        request = await verification_service.get_by_public_id(public_id=public_id)

        if not request or request.guild_id != guild_id:
            not_found_msg = config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Request not found."
            await interaction.response.send_message(content=not_found_msg, ephemeral=True)
            return

    await interaction.response.send_message(
        content=config.get(ConfigKey.REJECTION_SELECT_MESSAGE) or "Select the rejection reason:",
        view=build_rejection_view(public_id=public_id, config=config),
        ephemeral=True,
    )


async def handle_reject(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
    reason: str,
) -> None:
    """Handle verification rejection.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
        reason (str): Rejection reason.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    if not await authorize_and_defer(
        cog=cog,
        interaction=interaction,
        permission_error_key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
        permission_error_default="You do not have permission to reject verifications.",
    ):
        return

    # Serialized per request, see handle_accept
    async with (
        cog._request_locks.acquire(public_id),
        cog.bot.database.session() as session,
    ):
        ctx = await validate_mod_action(
            cog=cog, interaction=interaction, public_id=public_id, session=session
        )
        if not ctx:
            return

        config, request, verification_service = ctx
        # Captured before rejecting: the mod message may still show any of these
        previous = previous_statuses(config=config, guild=interaction.guild, request=request)

        await verification_service.reject(
            request_id=request.id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
            reason=reason,
            guild_name=interaction.guild.name,
        )
        await _notify_rejection(
            guild=interaction.guild, config=config, request=request, reason=reason
        )

        await _publish_decision(
            session=session,
            guild=interaction.guild,
            ctx=ctx,
            moderator=interaction.user,
            status_key=ConfigKey.STATUS_REJECTED,
            color=discord.Color.red(),
            previous=previous,
            reason=reason,
        )

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_REJECTED_CONFIRMATION)
            or "Verification rejected for {username}.",
            username=request.username,
        )
        await interaction.followup.send(content=confirmation, ephemeral=True)


def is_auto_rejected(request: VerificationRequest) -> bool:
    """Whether the request was rejected automatically (by the "Auto" reviewer).

    Args:
        request (VerificationRequest): Request to check.

    Returns:
        bool: True if auto-rejected.
    """
    return request.status == VerificationStatus.REJECTED and request.reviewed_by_username == "Auto"


async def review_refusal(
    service: VerificationService,
    config: dict[str, Any],
    guild_id: int,
    request: VerificationRequest | None,
) -> str | None:
    """Why a request cannot be sent back to manual review, if it cannot.

    Args:
        service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        guild_id (int): Guild of the interaction.
        request (VerificationRequest | None): Request looked up by public ID.

    Returns:
        str | None: Message for the moderator, or None when the review may proceed.
    """
    if not request or request.guild_id != guild_id:
        return config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Request not found."
    if not is_auto_rejected(request):
        return "This verification was not auto-rejected."
    latest = await service.get_latest_by_user(guild_id=guild_id, user_id=request.user_id)
    if not latest or latest.id != request.id:
        return "Only the user's latest verification can be reviewed."
    return None


async def _revert_for_review(
    session: AsyncSession,
    guild: discord.Guild,
    config: dict[str, Any],
    service: VerificationService,
    request: VerificationRequest,
) -> bool:
    """Revert the request to pending review and refresh the mod and tracker messages.

    Args:
        session (AsyncSession): Database session.
        guild (discord.Guild): Guild of the request.
        config (dict[str, Any]): Cog configuration.
        service (VerificationService): Verification service.
        request (VerificationRequest): Auto-rejected request.

    Returns:
        bool: False if the request could not be reverted.
    """
    # Save the original rejection reason before it gets cleared
    original_rejection_reason = request.rejection_reason
    if not await service.revert_to_pending_review(request_id=request.id, guild_name=guild.name):
        return False

    await update_mod_message_for_manual_review(
        guild=guild,
        request=request,
        config=config,
        public_id=request.public_id,
        original_rejection_reason=original_rejection_reason,
    )
    await session.commit()

    await update_tracker_message(
        guild=guild,
        config=config,
        verification_service=service,
        config_service=ConfigService(session=session),
    )
    await session.commit()
    return True


async def handle_review(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
) -> None:
    """Handle review of an auto-rejected verification.

    Allows moderators to manually review a verification that was
    auto-rejected, putting it back in pending state.

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    if not await authorize_and_defer(
        cog=cog,
        interaction=interaction,
        permission_error_key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
        permission_error_default="You do not have permission to review verifications.",
        ephemeral=True,
    ):
        return

    # Serialized per request, see handle_accept
    async with (
        cog._request_locks.acquire(public_id),
        cog.bot.database.session() as session,
    ):
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(
            guild_id=interaction.guild.id, config_service=config_service
        )

        verification_service = VerificationService(session=session)
        request = await verification_service.get_by_public_id(public_id=public_id)
        refusal = await review_refusal(
            service=verification_service,
            config=config,
            guild_id=interaction.guild.id,
            request=request,
        )
        if refusal or not request:
            await interaction.followup.send(content=refusal or "Request not found.", ephemeral=True)
            return

        reverted = await _revert_for_review(
            session=session,
            guild=interaction.guild,
            config=config,
            service=verification_service,
            request=request,
        )
        if not reverted:
            await interaction.followup.send(
                content="Could not revert the verification.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            content=f"Verification of {request.username} set for manual review.",
            ephemeral=True,
        )
