"""Procesamiento automático de verificaciones (auto-aprobación/rechazo)."""

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.views import AutoRejectReviewView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog
    from discord_bot.verification.models import VerificationRequest
    from discord_bot.verification.service import VerificationService

logger = logging.getLogger(__name__)


async def send_mod_ping_message(
    channel: discord.TextChannel,
    config: dict[str, Any],
) -> None:
    """Enviar mensaje de ping a moderadores cuando hay verificación pendiente.

    Args:
        channel: Canal de moderación
        config: Configuración del cog
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
    ping_message = format_message(ping_template, roles=roles_text)

    await channel.send(content=ping_message)


async def handle_auto_approval(
    cog: "VerificationCog",
    guild: discord.Guild,
    request: "VerificationRequest",
    verification_service: "VerificationService",
    config: dict[str, Any],
    mod_message: discord.Message,
    additional_content: str,
    embeds: list[discord.Embed],
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
) -> None:
    """Handle automatic approval of verification.

    Args:
        cog: Verification cog instance
        guild: Discord guild
        request: Verification request
        verification_service: Verification service
        config: Cog configuration
        mod_message: Moderation message to update
        additional_content: Additional content (player info, history)
        embeds: Screenshot embeds
        additional_sections: Secciones adicionales para el embed.
        sections_context: Contexto para placeholders de secciones.
    """
    await verification_service.approve(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
        guild_name=guild.name,
    )

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
                        f"[{guild.name}] Sin permisos para añadir rol {role.name} a {member.name}"
                    )

        for role_id in roles_remove or []:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    logger.warning(
                        f"[{guild.name}] Sin permisos para quitar rol {role.name} de {member.name}"
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

    delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
    if delete_messages:
        await mod_message.delete()
    else:
        approved_status = format_message(
            template=config.get(ConfigKey.STATUS_APPROVED),
            moderator="Auto",
        )
        verification_type = VerificationType(request.verification_type)
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_id=request.user_id,
            status=approved_status,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            additional_content=additional_content,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )
        for embed in main_embeds:
            embed.color = discord.Color.green()
        all_embeds = [*main_embeds, *embeds]
        await mod_message.edit(embeds=all_embeds, view=None)


async def handle_auto_rejection(
    cog: "VerificationCog",
    guild: discord.Guild,
    request: "VerificationRequest",
    verification_service: "VerificationService",
    config: dict[str, Any],
    mod_message: discord.Message,
    additional_content: str,
    embeds: list[discord.Embed],
    reason: str,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
) -> None:
    """Handle automatic rejection of verification.

    Args:
        cog: Verification cog instance
        guild: Discord guild
        request: Verification request
        verification_service: Verification service
        config: Cog configuration
        mod_message: Moderation message to update
        additional_content: Additional content (player info, history)
        embeds: Screenshot embeds
        reason: Rejection reason
        additional_sections: Secciones adicionales para el embed.
        sections_context: Contexto para placeholders de secciones.
    """
    await verification_service.reject(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
        reason=reason,
        guild_name=guild.name,
    )

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

    delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
    if delete_messages:
        await mod_message.delete()
    else:
        rejected_status = format_message(
            template=config.get(ConfigKey.STATUS_REJECTED),
            moderator="Auto",
            reason=reason,
        )
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        created_at_relative = f"<t:{int(request.created_at.timestamp())}:R>"
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_id=request.user_id,
            status=rejected_status,
            created_at=created_at_str,
            created_at_relative=created_at_relative,
            guild=guild,
            member=member,
            additional_content=additional_content,
            additional_sections=additional_sections,
            sections_context=sections_context,
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

        await mod_message.edit(embeds=all_embeds, view=view)


async def process_auto_verification(
    cog: "VerificationCog",
    guild: discord.Guild,
    request: "VerificationRequest",
    verification_service: "VerificationService",
    config: dict[str, Any],
    mod_message: discord.Message,
    additional_content: str,
    embeds: list[discord.Embed],
    should_approve: bool,
    rejection_reason: str | None,
    auto_approve: bool,
    auto_reject: bool,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
) -> bool:
    """Procesar auto-aprobación o auto-rechazo según las reglas.

    Args:
        cog: Instancia del cog de verificación
        guild: Guild de Discord
        request: Solicitud de verificación
        verification_service: Servicio de verificación
        config: Configuración del cog
        mod_message: Mensaje de moderación a actualizar
        additional_content: Contenido adicional
        embeds: Embeds de capturas
        should_approve: Si debería aprobarse
        rejection_reason: Motivo de rechazo si no aprueba
        auto_approve: Si auto-aprobación está habilitada
        auto_reject: Si auto-rechazo está habilitado
        additional_sections: Secciones adicionales para el embed
        sections_context: Contexto para placeholders de secciones

    Returns:
        True si se procesó automáticamente, False si requiere revisión manual
    """
    if should_approve and auto_approve:
        await handle_auto_approval(
            cog=cog,
            guild=guild,
            request=request,
            verification_service=verification_service,
            config=config,
            mod_message=mod_message,
            additional_content=additional_content,
            embeds=embeds,
            additional_sections=additional_sections,
            sections_context=sections_context,
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
            additional_content=additional_content,
            embeds=embeds,
            reason=rejection_reason or "Auto-rejected",
            additional_sections=additional_sections,
            sections_context=sections_context,
        )
        return True

    return False
