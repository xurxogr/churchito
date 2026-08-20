"""Automatic verification processing (auto-approval/rejection)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.utils import utc_timestamp
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import AutoRejectReviewView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


async def send_mod_ping_message(
    channel: discord.TextChannel,
    config: dict[str, Any],
) -> None:
    """Send ping message to moderators when there is a pending verification.

    Args:
        channel (discord.TextChannel): Moderation channel.
        config (dict[str, Any]): Cog configuration.
    """
    ping_template = config.get(ConfigKey.MOD_PING_MESSAGE)
    if not ping_template:
        return

    mod_role_ids = config.get(ConfigKey.MOD_ROLES) or []
    role_mentions = []

    for role_id in mod_role_ids:
        role = channel.guild.get_role(role_id)
        if role:
            role_mentions.append(role.mention)

    if not role_mentions:
        return

    roles_text = ", ".join(role_mentions)
    ping_message = format_message(template=ping_template, roles=roles_text)

    # Pinging the mod roles is the purpose of this message, so opt back into
    # the role pings the bot default suppresses
    await channel.send(content=ping_message, allowed_mentions=discord.AllowedMentions(roles=True))


async def _delete_mod_message(mod_message: discord.Message, guild_name: str) -> None:
    """Delete the moderation message, tolerating one already deleted.

    The approve/reject decision already ran when this is called: a mod message
    deleted by hand must not bubble up and roll the decision back after the
    member already received roles and the outcome DM.

    Args:
        mod_message (discord.Message): Moderation message to delete.
        guild_name (str): Guild name for logging.
    """
    try:
        await mod_message.delete()
    except discord.NotFound:
        logger.warning(f"[{guild_name}] Mod message already deleted: {mod_message.id}")


async def _edit_mod_message(
    mod_message: discord.Message,
    guild_name: str,
    embeds: list[discord.Embed],
    view: discord.ui.View | None,
) -> None:
    """Update the moderation message, tolerating one already deleted.

    Same rationale as ``_delete_mod_message``: the decision is already made and
    must survive the status embed having nowhere to land.

    Args:
        mod_message (discord.Message): Moderation message to update.
        guild_name (str): Guild name for logging.
        embeds (list[discord.Embed]): Embeds to show.
        view (discord.ui.View | None): View to attach, if any.
    """
    try:
        await mod_message.edit(embeds=embeds, view=view)
    except discord.NotFound:
        logger.warning(f"[{guild_name}] Mod message already deleted: {mod_message.id}")


async def handle_auto_approval(
    cog: VerificationCog,
    guild: discord.Guild,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    mod_message: discord.Message,
    embeds: list[discord.Embed],
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
    check_statuses: dict[str, str] | None = None,
    api_status: str = "",
) -> None:
    """Handle automatic approval of verification.

    Args:
        cog (VerificationCog): Verification cog instance.
        guild (discord.Guild): Discord guild.
        request (VerificationRequest): Verification request.
        verification_service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        mod_message (discord.Message): Moderation message to update.
        embeds (list[discord.Embed]): Screenshot embeds.
        additional_sections (list[dict[str, Any]] | None): Additional sections for the embed.
        sections_context (dict[str, Any] | None): Context for section placeholders.
        check_statuses (dict[str, str] | None): Status placeholders for checks.
        api_status (str): API status message placeholder.
    """
    await verification_service.approve(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
        guild_name=guild.name,
    )
    # Persist the approval before touching Discord: a failing role edit, DM or
    # mod message update below would otherwise roll the request back to
    # awaiting screenshots after the member already got the roles and the
    # approval DM, and the still-armed screenshot timer would later reject it
    await verification_service.commit()

    member = guild.get_member(request.user_id)
    if member:
        if request.verification_type == VerificationType.REGULAR:
            roles_add = config.get(ConfigKey.REGULAR_ROLES_ADD)
            roles_remove = config.get(ConfigKey.REGULAR_ROLES_REMOVE)
            approval_msg_key = ConfigKey.APPROVAL_MESSAGE_REGULAR
        else:
            roles_add = config.get(ConfigKey.ALLY_ROLES_ADD)
            roles_remove = config.get(ConfigKey.ALLY_ROLES_REMOVE)
            approval_msg_key = ConfigKey.APPROVAL_MESSAGE_ALLY

        for role_id in roles_add or []:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    logger.warning(
                        f"[{guild.name}] No permission to add role {role.name} to {member.name}"
                    )

        for role_id in roles_remove or []:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    logger.warning(
                        f"[{guild.name}] No permission to remove role "
                        f"{role.name} from {member.name}"
                    )

        approval_msg = format_message(
            template=config.get(approval_msg_key),
            username=request.username,
            server_name=guild.name,
        )
        try:
            await member.send(content=approval_msg)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            # Best effort: the approval is already committed, and a rendered
            # template pushed over the 2000-character DM limit must not stop
            # the mod message update and the intake cleanup that follow
            logger.warning(f"[{guild.name}] Could not DM the approval to {member.name}: {e}")

    delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
    if delete_messages:
        await _delete_mod_message(mod_message=mod_message, guild_name=guild.name)
    else:
        approved_status = format_message(
            template=config.get(ConfigKey.STATUS_APPROVED),
            moderator="Auto",
            moderator_display_name="Auto",
        )
        verification_type = VerificationType(request.verification_type)
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{utc_timestamp(request.created_at)}:R>"
        user_display_name = member.display_name if member else request.username
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_display_name=user_display_name,
            user_id=request.user_id,
            status=approved_status,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            additional_sections=additional_sections,
            sections_context=sections_context,
            api_status=api_status,
            steam_profile_url=request.steam_profile_url or "",
            **(check_statuses or {}),
        )
        for embed in main_embeds:
            embed.color = discord.Color.green()
        all_embeds = [*main_embeds, *embeds]
        await _edit_mod_message(
            mod_message=mod_message, guild_name=guild.name, embeds=all_embeds, view=None
        )


async def handle_auto_rejection(
    cog: VerificationCog,
    guild: discord.Guild,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    mod_message: discord.Message,
    embeds: list[discord.Embed],
    reason: str,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
    check_statuses: dict[str, str] | None = None,
    api_status: str = "",
) -> None:
    """Handle automatic rejection of verification.

    Args:
        cog (VerificationCog): Verification cog instance.
        guild (discord.Guild): Discord guild.
        request (VerificationRequest): Verification request.
        verification_service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        mod_message (discord.Message): Moderation message to update.
        embeds (list[discord.Embed]): Screenshot embeds.
        reason (str): Rejection reason.
        additional_sections (list[dict[str, Any]] | None): Additional sections for the embed.
        sections_context (dict[str, Any] | None): Context for section placeholders.
        check_statuses (dict[str, str] | None): Status placeholders for checks.
        api_status (str): API status message placeholder.
    """
    await verification_service.reject(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
        reason=reason,
        guild_name=guild.name,
    )
    # Persist the rejection before touching Discord: a failing DM or mod
    # message update below would otherwise roll the request back to awaiting
    # screenshots after the member was already told it was rejected
    await verification_service.commit()

    member = guild.get_member(request.user_id)
    verification_type = VerificationType(request.verification_type)
    type_display = get_verification_type_display(verification_type=verification_type, config=config)
    if member:
        rejection_msg = format_message(
            template=config.get(ConfigKey.REJECTION_MESSAGE),
            username=request.username,
            server_name=guild.name,
            verification_type=type_display,
            reason=reason,
        )
        try:
            await member.send(content=rejection_msg)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            # Best effort: the rejection is already committed, and the reason
            # can stack several configured messages over the 2000-character
            # DM limit — that must not stop the mod message update and the
            # intake cleanup that follow
            logger.warning(f"[{guild.name}] Could not DM the rejection to {member.name}: {e}")

    delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
    if delete_messages:
        await _delete_mod_message(mod_message=mod_message, guild_name=guild.name)
    else:
        rejected_status = format_message(
            template=config.get(ConfigKey.STATUS_REJECTED),
            moderator="Auto",
            moderator_display_name="Auto",
            reason=reason,
        )
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{utc_timestamp(request.created_at)}:R>"
        user_display_name = member.display_name if member else request.username
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_display_name=user_display_name,
            user_id=request.user_id,
            status=rejected_status,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            additional_sections=additional_sections,
            sections_context=sections_context,
            api_status=api_status,
            steam_profile_url=request.steam_profile_url or "",
            **(check_statuses or {}),
        )
        for embed in main_embeds:
            embed.color = discord.Color.red()
        all_embeds = [*main_embeds, *embeds]

        review_window = config.get(ConfigKey.AUTO_REJECT_REVIEW_WINDOW, 0)
        if review_window and review_window > 0:
            review_label = config.get(ConfigKey.REVIEW_BUTTON_TEXT) or "Revisar"
            view: discord.ui.View | None = AutoRejectReviewView(
                public_id=request.public_id,
                review_label=review_label,
                timeout_minutes=review_window,
            )
        else:
            view = None

        await _edit_mod_message(
            mod_message=mod_message, guild_name=guild.name, embeds=all_embeds, view=view
        )


async def process_auto_verification(
    cog: VerificationCog,
    guild: discord.Guild,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    mod_message: discord.Message,
    embeds: list[discord.Embed],
    should_approve: bool,
    rejection_reason: str | None,
    auto_approve: bool,
    auto_reject: bool,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
    check_statuses: dict[str, str] | None = None,
    api_status: str = "",
) -> bool:
    """Process auto-approval or auto-rejection based on rules.

    Args:
        cog (VerificationCog): Verification cog instance.
        guild (discord.Guild): Discord guild.
        request (VerificationRequest): Verification request.
        verification_service (VerificationService): Verification service.
        config (dict[str, Any]): Cog configuration.
        mod_message (discord.Message): Moderation message to update.
        embeds (list[discord.Embed]): Screenshot embeds.
        should_approve (bool): Whether it should be approved.
        rejection_reason (str | None): Rejection reason if not approved.
        auto_approve (bool): Whether auto-approval is enabled.
        auto_reject (bool): Whether auto-rejection is enabled.
        additional_sections (list[dict[str, Any]] | None): Additional sections for the embed.
        sections_context (dict[str, Any] | None): Context for section placeholders.
        check_statuses (dict[str, str] | None): Status placeholders for checks.
        api_status (str): API status message placeholder.

    Returns:
        bool: True if processed automatically, False if manual review required.
    """
    if should_approve and auto_approve:
        await handle_auto_approval(
            cog=cog,
            guild=guild,
            request=request,
            verification_service=verification_service,
            config=config,
            mod_message=mod_message,
            embeds=embeds,
            additional_sections=additional_sections,
            sections_context=sections_context,
            check_statuses=check_statuses,
            api_status=api_status,
        )
        return True
    elif not should_approve and auto_reject:
        await handle_auto_rejection(
            cog=cog,
            guild=guild,
            request=request,
            verification_service=verification_service,
            config=config,
            mod_message=mod_message,
            embeds=embeds,
            reason=rejection_reason or "Auto-rejected",
            additional_sections=additional_sections,
            sections_context=sections_context,
            check_statuses=check_statuses,
            api_status=api_status,
        )
        return True

    return False
