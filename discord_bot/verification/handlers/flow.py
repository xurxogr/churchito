"""Main verification flow and moderator actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import has_any_role, is_valid_discord_cdn_url
from discord_bot.verification.api_client import call_verification_api
from discord_bot.verification.enums import (
    ConfigKey,
    VerificationStatus,
    VerificationType,
)
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.handlers.mod_messages import (
    update_mod_message_for_manual_review,
    update_mod_message_for_review,
    update_mod_message_status,
    update_tracker_message,
)
from discord_bot.verification.handlers.utils import (
    calculate_expires_timestamp,
    get_ready_for_approval_status,
)
from discord_bot.verification.models import VerificationAPIResult, VerificationRequest
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
    lock = await cog.get_user_lock(user.id)
    async with lock:
        await _handle_verification_start_locked(cog, interaction, guild, user, verification_type)


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

    if config.get(ConfigKey.VERIFICATION_ENABLED) is False:
        await interaction.followup.send(
            config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
        )
        return

    mod_channel = cog._get_mod_channel(guild=guild, config=config)
    if not mod_channel:
        await interaction.followup.send(
            config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
        )
        return

    type_display = get_verification_type_display(verification_type=verification_type, config=config)

    blocking_roles = config.get(ConfigKey.BLOCKING_ROLES) or []
    if blocking_roles and isinstance(user, discord.Member):
        blocking_role_ids = set(blocking_roles)
        user_role_ids = {role.id for role in user.roles}
        if user_role_ids & blocking_role_ids:
            await interaction.followup.send(
                config.get(ConfigKey.ALREADY_VERIFIED_MESSAGE) or "", ephemeral=True
            )
            return

    async with cog.bot.database.session() as session:
        verification_service = VerificationService(session=session)

        pending = await verification_service.get_pending_by_user(guild_id=guild.id, user_id=user.id)
        if pending:
            await interaction.followup.send(
                config.get(ConfigKey.ALREADY_PENDING_MESSAGE) or "", ephemeral=True
            )
            return

        pending_any = await verification_service.get_any_pending_by_user(user_id=user.id)
        if pending_any:
            await interaction.followup.send(
                config.get(ConfigKey.PENDING_IN_OTHER_SERVER_MESSAGE)
                or "You already have an ongoing verification in another server.",
                ephemeral=True,
            )
            return

        request = await verification_service.create_request(
            guild_id=guild.id,
            user_id=user.id,
            username=user.name,
            guild_name=guild.name,
            verification_type=verification_type,
        )

        timeout_minutes = config.get(ConfigKey.SCREENSHOT_TIMEOUT_MINUTES) or 0
        expires_relative = calculate_expires_timestamp(
            created_at=request.created_at, timeout_minutes=timeout_minutes
        )

        dm_template = (
            config.get(ConfigKey.DM_INSTRUCTIONS_MESSAGE)
            if verification_type == VerificationType.REGULAR
            else config.get(ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE)
        )
        formatted_dm = format_message(
            template=dm_template,
            username=user.name,
            user_mention=user.mention,
            server_name=guild.name,
            verification_type=type_display,
            expires=expires_relative,
        )

        try:
            await user.send(content=formatted_dm)
        except discord.Forbidden:
            await verification_service.cancel(request_id=request.id, guild_name=guild.name)
            await session.commit()
            await interaction.followup.send(
                config.get(ConfigKey.DM_DISABLED_MESSAGE) or "", ephemeral=True
            )
            return

        cog._pending_dm_verifications[user.id] = (guild.id, request.id)

        if timeout_minutes > 0:
            cog.start_screenshot_timer(
                request_id=request.id,
                guild_id=guild.id,
                user_id=user.id,
                timeout_minutes=timeout_minutes,
            )

        status_text = config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or ""
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"
        member = user if isinstance(user, discord.Member) else None
        user_display_name = member.display_name if member else user.display_name
        mod_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=user.name,
            user_mention=user.mention,
            user_display_name=user_display_name,
            user_id=user.id,
            status=status_text,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            api_status="",
        )

        mod_message = await mod_channel.send(embeds=mod_embeds)
        await verification_service.set_mod_message_id(
            request_id=request.id, message_id=mod_message.id
        )

        await session.commit()

        config_service = ConfigService(session=session)
        await update_tracker_message(
            guild=guild,
            config=config,
            verification_service=verification_service,
            config_service=config_service,
        )
        await session.commit()

    started_message = config.get(ConfigKey.VERIFICATION_STARTED_MESSAGE) or ""
    await interaction.followup.send(started_message, ephemeral=True)


async def handle_dm_screenshots(
    cog: VerificationCog,
    message: discord.Message,
    guild_id: int,
    request_id: int,
) -> None:
    """Process DM message with screenshots.

    Args:
        cog (VerificationCog): Cog instance.
        message (discord.Message): Received message.
        guild_id (int): Guild ID.
        request_id (int): Request ID.
    """
    image_attachments = [
        a for a in message.attachments if a.content_type and a.content_type.startswith("image/")
    ]

    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(guild_id=guild_id, config_service=config_service)

        if len(image_attachments) != 2:
            formatted = format_message(
                template=config.get(ConfigKey.WRONG_IMAGES_MESSAGE),
                username=message.author.name,
            )
            await message.channel.send(content=formatted)
            return

        url1 = image_attachments[0].url
        url2 = image_attachments[1].url

        guild = cog.bot.get_guild(guild_id)
        guild_name = guild.name if guild else f"Guild {guild_id}"

        if not is_valid_discord_cdn_url(url1) or not is_valid_discord_cdn_url(url2):
            logger.warning(
                f"[{guild_name}] Invalid screenshot URLs for {message.author.name}: "
                f"{url1[:50]}..., {url2[:50]}..."
            )
            formatted = format_message(
                template=config.get(ConfigKey.WRONG_IMAGES_MESSAGE),
                username=message.author.name,
            )
            await message.channel.send(content=formatted)
            return

        del cog._pending_dm_verifications[message.author.id]

        cog.cancel_screenshot_timer(request_id)

        verification_service = VerificationService(session=session)

        request = await verification_service.update_screenshots(
            request_id=request_id,
            url1=url1,
            url2=url2,
            guild_name=guild_name,
        )

        if not request:
            await message.channel.send(content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE))
            return

        server_name = guild_name if guild else "the server"
        formatted_received = format_message(
            template=config.get(ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE),
            username=message.author.name,
            server_name=server_name,
        )
        await message.channel.send(content=formatted_received)

        api_result: VerificationAPIResult | None = None
        verification_settings = cog.bot.settings.verification
        if verification_settings.api_url:
            api_result = await call_verification_api(
                url=verification_settings.api_url,
                api_key=verification_settings.api_key or None,
                image1_url=url1,
                image2_url=url2,
                timeout_seconds=verification_settings.api_timeout,
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

        if guild and request.mod_message_id:
            mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
            if mod_channel_id:
                mod_channel = guild.get_channel(mod_channel_id)
                if mod_channel and isinstance(mod_channel, discord.TextChannel):
                    auto_processed = await update_mod_message_for_review(
                        cog=cog,
                        channel=mod_channel,
                        request=request,
                        verification_service=verification_service,
                        config=config,
                        api_result=api_result,
                    )
                    if auto_processed:
                        await session.commit()
                        await update_tracker_message(
                            guild=guild,
                            config=config,
                            verification_service=verification_service,
                            config_service=config_service,
                        )
                        return

        await session.commit()

        if guild:
            await update_tracker_message(
                guild=guild,
                config=config,
                verification_service=verification_service,
                config_service=config_service,
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

        # Determine possible previous status texts
        # Could be either "pending review" or "ready for approval" (when OCR passed)
        # Also include auto-rejected status in case Review didn't properly update
        pending_review_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
        ready_for_approval_status = get_ready_for_approval_status(
            config=config, guild=interaction.guild
        )
        auto_rejected_status = format_message(
            template=config.get(ConfigKey.STATUS_REJECTED),
            moderator="Auto",
            reason=request.rejection_reason or "",
        )

        await verification_service.approve(
            request_id=request.id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
            guild_name=interaction.guild.name,
        )

        failed_roles: list[str] = []
        member = interaction.guild.get_member(request.user_id)
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
                role = interaction.guild.get_role(role_id)
                if not role:
                    logger.warning(f"[{interaction.guild.name}] Role not found (ID: {role_id})")
                    continue
                try:
                    await member.add_roles(role)
                except discord.Forbidden as e:
                    failed_roles.append(f"@{role.name} (add)")
                    logger.warning(
                        f"Could not add role {role.name} ({role_id}): {e}. "
                        f"Verify the bot has 'Manage Roles' permission and that "
                        f"its role is above @{role.name} in the hierarchy."
                    )

            for role_id in roles_remove or []:
                role = interaction.guild.get_role(role_id)
                if not role:
                    logger.warning(f"[{interaction.guild.name}] Role not found (ID: {role_id})")
                    continue
                try:
                    await member.remove_roles(role)
                except discord.Forbidden as e:
                    failed_roles.append(f"@{role.name} (remove)")
                    logger.warning(
                        f"Could not remove role {role.name} ({role_id}): {e}. "
                        f"Verify the bot has 'Manage Roles' permission and that "
                        f"its role is above @{role.name} in the hierarchy."
                    )

            formatted = format_message(
                template=config.get(approval_msg_key),
                username=request.username,
                server_name=interaction.guild.name,
            )
            try:
                await member.send(content=formatted)
            except discord.Forbidden:
                pass

        approved_status = format_message(
            template=config.get(ConfigKey.STATUS_APPROVED),
            moderator=interaction.user.name,
        )
        await update_mod_message_status(
            guild=interaction.guild,
            request=request,
            config=config,
            status=approved_status,
            color=discord.Color.green(),
            previous_statuses=[
                ready_for_approval_status,
                pending_review_status,
                auto_rejected_status,
            ],
        )

        await session.commit()

        config_service = ConfigService(session=session)
        await update_tracker_message(
            guild=interaction.guild,
            config=config,
            verification_service=verification_service,
            config_service=config_service,
        )
        await session.commit()

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_APPROVED_CONFIRMATION)
            or "Verification approved for {username}.",
            username=request.username,
        )
        if failed_roles:
            roles_warning = ", ".join(failed_roles)
            await interaction.followup.send(
                f"{confirmation}\n\n"
                f"⚠️ **Warning:** Could not modify some roles: {roles_warning}\n"
                f"Verify that:\n"
                f"• The bot has the **Manage Roles** permission\n"
                f"• The bot's role is **above** these roles in the hierarchy",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(confirmation, ephemeral=True)


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

        # Determine possible previous status texts
        # Also include auto-rejected status in case Review didn't properly update
        pending_review_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pending review"
        ready_for_approval_status = get_ready_for_approval_status(
            config=config, guild=interaction.guild
        )
        auto_rejected_status = format_message(
            template=config.get(ConfigKey.STATUS_REJECTED),
            moderator="Auto",
            reason=request.rejection_reason or "",
        )

        await verification_service.reject(
            request_id=request.id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
            reason=reason,
            guild_name=interaction.guild.name,
        )

        member = interaction.guild.get_member(request.user_id)
        if member:
            type_display = get_verification_type_display(
                verification_type=VerificationType(request.verification_type), config=config
            )
            formatted = format_message(
                template=config.get(ConfigKey.REJECTION_MESSAGE),
                username=request.username,
                server_name=interaction.guild.name,
                verification_type=type_display,
                reason=reason,
            )
            try:
                await member.send(content=formatted)
            except discord.Forbidden:
                pass

        rejected_status = format_message(
            template=config.get(ConfigKey.STATUS_REJECTED),
            moderator=interaction.user.name,
            reason=reason,
        )
        await update_mod_message_status(
            guild=interaction.guild,
            request=request,
            config=config,
            status=rejected_status,
            color=discord.Color.red(),
            previous_statuses=[
                ready_for_approval_status,
                pending_review_status,
                auto_rejected_status,
            ],
        )

        await session.commit()

        config_service = ConfigService(session=session)
        await update_tracker_message(
            guild=interaction.guild,
            config=config,
            verification_service=verification_service,
            config_service=config_service,
        )
        await session.commit()

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
