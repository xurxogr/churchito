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


async def validate_mod_action(
    cog: VerificationCog,
    interaction: discord.Interaction,
    public_id: str,
    session: AsyncSession,
    permission_error_key: ConfigKey,
    permission_error_default: str,
) -> ModActionContext | None:
    """Validate and prepare context for moderation actions.

    Performs all common validations for approve/reject:
    - Verify moderator permissions
    - Defer the interaction
    - Get the request
    - Verify it exists and is pending review

    Args:
        cog (VerificationCog): Cog instance.
        interaction (discord.Interaction): Moderator interaction.
        public_id (str): Public request ID (NanoID).
        session (AsyncSession): Database session.
        permission_error_key (ConfigKey): Permission error message key.
        permission_error_default (str): Default message if not configured.

    Returns:
        ModActionContext | None: Validated context or None if any validation failed.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None

    config_service = ConfigService(session=session)
    config = await cog._get_all_config(guild_id=interaction.guild.id, config_service=config_service)

    if not has_any_role(member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []):
        await interaction.response.send_message(
            content=config.get(permission_error_key) or permission_error_default,
            ephemeral=True,
        )
        return None

    await interaction.response.defer()

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

    async with cog.bot.database.session() as session:
        ctx = await validate_mod_action(
            cog=cog,
            interaction=interaction,
            public_id=public_id,
            session=session,
            permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
            permission_error_default="You do not have permission to approve verifications.",
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

    reasons: list[str] = []
    rejection_reason_keys = [
        ConfigKey.REJECT_WRONG_CAPTURES,
        ConfigKey.REJECT_NAME_MISMATCH,
        ConfigKey.REJECT_HAS_REGIMENT,
        ConfigKey.REJECT_TIME_DIFF,
        ConfigKey.REJECT_WRONG_SHARD,
        ConfigKey.REJECT_WRONG_FACTION,
        ConfigKey.REJECT_STEAM_PRIVATE,
    ]
    for key in rejection_reason_keys:
        reason = config.get(key) or ""
        if reason and reason.strip():
            if key == ConfigKey.REJECT_WRONG_SHARD:
                expected_shard = config.get(ConfigKey.VERIFICATION_SHARD) or ""
                if expected_shard:
                    reason = reason.replace("{shard}", expected_shard)
                else:
                    continue
            elif key == ConfigKey.REJECT_WRONG_FACTION:
                expected_faction = config.get(ConfigKey.VERIFICATION_FACTION) or ""
                if expected_faction:
                    reason = reason.replace("{faction}", expected_faction)
                else:
                    continue
            reasons.append(reason)

    select_message = (
        config.get(ConfigKey.REJECTION_SELECT_MESSAGE) or "Select the rejection reason:"
    )
    placeholder = (
        config.get(ConfigKey.REJECTION_SELECT_PLACEHOLDER) or "Select the rejection reason..."
    )
    other_label = config.get(ConfigKey.REJECTION_OTHER_LABEL) or "Other reason..."
    other_description = config.get(ConfigKey.REJECTION_OTHER_DESCRIPTION) or "Write a custom reason"
    modal_title = config.get(ConfigKey.REJECTION_MODAL_TITLE) or "Rejection Reason"
    modal_label = config.get(ConfigKey.REJECTION_MODAL_LABEL) or "Reason"
    modal_placeholder = (
        config.get(ConfigKey.REJECTION_MODAL_PLACEHOLDER)
        or "Explain why the verification is being rejected..."
    )

    view = RejectionReasonView(
        public_id=public_id,
        reasons=reasons,
        other_label=other_label,
        other_description=other_description,
        placeholder=placeholder,
        modal_title=modal_title,
        modal_label=modal_label,
        modal_placeholder=modal_placeholder,
    )
    await interaction.response.send_message(
        content=select_message,
        view=view,
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

    async with cog.bot.database.session() as session:
        ctx = await validate_mod_action(
            cog=cog,
            interaction=interaction,
            public_id=public_id,
            session=session,
            permission_error_key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
            permission_error_default="You do not have permission to reject verifications.",
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

    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(
            guild_id=interaction.guild.id, config_service=config_service
        )

        if not has_any_role(
            member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []
        ):
            await interaction.response.send_message(
                content=config.get(ConfigKey.NO_PERMISSION_REJECT_MESSAGE)
                or "You do not have permission to review verifications.",
                ephemeral=True,
            )
            return

        verification_service = VerificationService(session=session)
        request = await verification_service.get_by_public_id(public_id=public_id)

        if not request or request.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Request not found.",
                ephemeral=True,
            )
            return

        if request.status != VerificationStatus.REJECTED or request.reviewed_by_username != "Auto":
            await interaction.response.send_message(
                content="This verification was not auto-rejected.",
                ephemeral=True,
            )
            return

        latest = await verification_service.get_latest_by_user(
            guild_id=interaction.guild.id,
            user_id=request.user_id,
        )
        if not latest or latest.id != request.id:
            await interaction.response.send_message(
                content="Only the user's latest verification can be reviewed.",
                ephemeral=True,
            )
            return

        # Save the original rejection reason before it gets cleared
        original_rejection_reason = request.rejection_reason

        reverted = await verification_service.revert_to_pending_review(
            request_id=request.id, guild_name=interaction.guild.name
        )
        if not reverted:
            await interaction.response.send_message(
                content="Could not revert the verification.",
                ephemeral=True,
            )
            return

        await update_mod_message_for_manual_review(
            guild=interaction.guild,
            request=request,
            config=config,
            public_id=request.public_id,
            original_rejection_reason=original_rejection_reason,
        )

        await session.commit()

        await update_tracker_message(
            guild=interaction.guild,
            config=config,
            verification_service=verification_service,
            config_service=config_service,
        )
        await session.commit()

        await interaction.response.send_message(
            content=f"Verification of {request.username} set for manual review.",
            ephemeral=True,
        )
