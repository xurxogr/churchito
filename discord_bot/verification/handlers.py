"""Manejadores de flujo de verificacion."""

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import has_any_role
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.formatters import format_message, get_verification_type_display
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import ModReviewView, RejectionReasonView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


class ModActionContext(NamedTuple):
    """Contexto validado para acciones de moderacion."""

    config: dict[str, Any]
    request: "VerificationRequest"
    service: "VerificationService"


async def validate_mod_action(
    cog: "VerificationCog",
    interaction: discord.Interaction,
    request_id: int,
    session: AsyncSession,
    permission_error_key: ConfigKey,
    permission_error_default: str,
) -> ModActionContext | None:
    """Validar y preparar contexto para acciones de moderacion.

    Realiza todas las validaciones comunes para aprobar/rechazar:
    - Verificar permisos de moderador
    - Defer la interaccion
    - Obtener la solicitud
    - Verificar que existe y esta pendiente de revision

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interaccion del moderador.
        request_id (int): ID de la solicitud.
        session (AsyncSession): Sesion de base de datos.
        permission_error_key (ConfigKey): Clave del mensaje de error de permisos.
        permission_error_default (str): Mensaje por defecto si no esta configurado.

    Returns:
        ModActionContext | None: Contexto validado o None si fallo alguna validacion.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None

    config_service = ConfigService(session=session)
    config = await cog._get_all_config(guild_id=interaction.guild.id, config_service=config_service)

    # Verificar permisos de moderador
    if not has_any_role(member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []):
        await interaction.response.send_message(
            content=config.get(permission_error_key) or permission_error_default,
            ephemeral=True,
        )
        return None

    await interaction.response.defer()

    verification_service = VerificationService(session=session)
    request = await verification_service.get_request(request_id=request_id)

    if not request or request.guild_id != interaction.guild.id:
        await interaction.followup.send(
            content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Solicitud no encontrada.",
            ephemeral=True,
        )
        return None

    if request.status != VerificationStatus.PENDING_REVIEW:
        await interaction.followup.send(
            content=config.get(ConfigKey.REQUEST_ALREADY_PROCESSED_MESSAGE)
            or "Esta solicitud ya fue procesada.",
            ephemeral=True,
        )
        return None

    return ModActionContext(config=config, request=request, service=verification_service)


async def handle_verification_start(
    cog: "VerificationCog",
    interaction: discord.Interaction,
    verification_type: VerificationType,
) -> None:
    """Manejar inicio de verificacion cuando el usuario hace clic en un boton.

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interaccion del usuario.
        verification_type (VerificationType): Tipo de verificacion.
    """
    if not interaction.guild or not interaction.user:
        return

    guild = interaction.guild
    user = interaction.user

    # Verificar si el cog esta habilitado
    if not await cog._is_cog_enabled(guild.id):
        return

    await interaction.response.defer(ephemeral=True)

    # Obtener toda la configuracion de una vez
    config = await cog._get_all_config(guild.id)

    # Verificar si la verificacion esta habilitada
    if config.get(ConfigKey.VERIFICATION_ENABLED) is False:
        await interaction.followup.send(
            config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
        )
        return

    # Verificar que el canal de moderacion esta configurado y accesible
    mod_channel = cog._get_mod_channel(guild=guild, config=config)
    if not mod_channel:
        await interaction.followup.send(
            config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
        )
        return

    # Obtener nombre del tipo de verificacion para mensajes
    type_display = get_verification_type_display(verification_type=verification_type, config=config)

    # Verificar si el usuario ya tiene los roles de verificacion
    if config.get(ConfigKey.BLOCK_ALREADY_VERIFIED) and isinstance(user, discord.Member):
        roles_to_add = (
            config.get(ConfigKey.REGULAR_ROLES_ADD)
            if verification_type == VerificationType.REGULAR
            else config.get(ConfigKey.ALLY_ROLES_ADD)
        )

        if roles_to_add:
            user_role_ids = {role.id for role in user.roles}
            has_all_roles = all(role_id in user_role_ids for role_id in roles_to_add)
            if has_all_roles:
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

        request = await verification_service.create_request(
            guild_id=guild.id,
            user_id=user.id,
            username=user.name,
            verification_type=verification_type,
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
        )

        try:
            await user.send(content=formatted_dm)
        except discord.Forbidden:
            await verification_service.cancel(request.id)
            await session.commit()
            await interaction.followup.send(
                config.get(ConfigKey.DM_DISABLED_MESSAGE) or "", ephemeral=True
            )
            return

        cog._pending_dm_verifications[user.id] = (guild.id, request.id)

        # Enviar notificacion al canal de moderacion
        status_text = config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or ""
        formatted_mod = format_message(
            template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
            username=user.name,
            user_mention=user.mention,
            verification_type=type_display,
            status=status_text,
        )

        mod_message = await mod_channel.send(content=formatted_mod)
        await verification_service.set_mod_message_id(
            request_id=request.id, message_id=mod_message.id
        )

        await session.commit()

    started_message = config.get(ConfigKey.VERIFICATION_STARTED_MESSAGE) or ""
    await interaction.followup.send(started_message, ephemeral=True)


async def handle_dm_screenshots(
    cog: "VerificationCog",
    message: discord.Message,
    guild_id: int,
    request_id: int,
) -> None:
    """Procesar mensaje DM con capturas de pantalla.

    Args:
        cog (VerificationCog): Instancia del cog.
        message (discord.Message): Mensaje recibido.
        guild_id (int): ID del guild.
        request_id (int): ID de la solicitud.
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

        del cog._pending_dm_verifications[message.author.id]

        verification_service = VerificationService(session=session)

        request = await verification_service.update_screenshots(
            request_id=request_id,
            url1=image_attachments[0].url,
            url2=image_attachments[1].url,
        )

        if not request:
            await message.channel.send(content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE))
            return

        guild = cog.bot.get_guild(guild_id)
        server_name = guild.name if guild else "el servidor"
        formatted_received = format_message(
            template=config.get(ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE),
            username=message.author.name,
            server_name=server_name,
        )
        await message.channel.send(content=formatted_received)

        if guild and request.mod_message_id:
            mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
            if mod_channel_id:
                mod_channel = guild.get_channel(mod_channel_id)
                if mod_channel and isinstance(mod_channel, discord.TextChannel):
                    await update_mod_message_for_review(
                        cog=cog,
                        channel=mod_channel,
                        request=request,
                        verification_service=verification_service,
                        config=config,
                    )

        await session.commit()


async def update_mod_message_for_review(
    cog: "VerificationCog",
    channel: discord.TextChannel,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
) -> None:
    """Actualizar mensaje de moderacion cuando se reciben las capturas.

    Args:
        cog (VerificationCog): Instancia del cog.
        channel (discord.TextChannel): Canal de moderacion.
        request (VerificationRequest): Solicitud de verificacion.
        verification_service (VerificationService): Servicio de verificacion.
        config (dict[str, Any]): Configuracion del cog.
    """
    if not request.mod_message_id:
        return

    try:
        mod_message = await channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")
        return

    type_display = get_verification_type_display(
        verification_type=VerificationType(request.verification_type), config=config
    )
    status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
    formatted = format_message(
        template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        verification_type=type_display,
        status=status_text,
    )

    # Agregar capturas
    formatted += f"\n{request.screenshot_1_url} {request.screenshot_2_url}"

    # Agregar historial
    history = await verification_service.get_user_history(
        guild_id=request.guild_id, user_id=request.user_id
    )
    past_requests = [r for r in history if r.id != request.id]

    if past_requests:
        history_label = config.get(ConfigKey.HISTORY_LABEL) or "Historial"
        formatted += f"\n**{history_label}:**"
        for past in past_requests[:5]:
            status_emoji = {
                VerificationStatus.APPROVED: "✅",
                VerificationStatus.REJECTED: "❌",
                VerificationStatus.CANCELLED: "🚫",
            }.get(VerificationStatus(past.status), "❓")
            timestamp = past.reviewed_at or past.created_at
            date_str = timestamp.strftime("%Y-%m-%d %H:%M")
            moderator = past.reviewed_by_username or ""
            past_type_display = get_verification_type_display(
                verification_type=VerificationType(past.verification_type), config=config
            )
            formatted += f"\n{status_emoji} {past_type_display} - {moderator} ({date_str})"
            if past.rejection_reason:
                formatted += f" - {past.rejection_reason}"

    accept_label = config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Aceptar"
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Rechazar"
    view = ModReviewView(
        request_id=request.id, accept_label=accept_label, reject_label=reject_label
    )

    await mod_message.edit(content=formatted, view=view)


async def handle_accept(
    cog: "VerificationCog",
    interaction: discord.Interaction,
    request_id: int,
) -> None:
    """Manejar aprobacion de verificacion.

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interaccion del moderador.
        request_id (int): ID de la solicitud.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    async with cog.bot.database.session() as session:
        ctx = await validate_mod_action(
            cog=cog,
            interaction=interaction,
            request_id=request_id,
            session=session,
            permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
            permission_error_default="No tienes permisos para aprobar verificaciones.",
        )
        if not ctx:
            return

        config, request, verification_service = ctx

        await verification_service.approve(
            request_id=request_id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
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
                    logger.warning(f"Rol no encontrado: {role_id}")
                    continue
                try:
                    await member.add_roles(role)
                except discord.Forbidden as e:
                    failed_roles.append(f"@{role.name} (agregar)")
                    logger.warning(
                        f"No se pudo agregar rol {role.name} ({role_id}): {e}. "
                        f"Verifica que el bot tenga permiso 'Gestionar roles' y que "
                        f"su rol este por encima de @{role.name} en la jerarquia."
                    )

            for role_id in roles_remove or []:
                role = interaction.guild.get_role(role_id)
                if not role:
                    logger.warning(f"Rol no encontrado: {role_id}")
                    continue
                try:
                    await member.remove_roles(role)
                except discord.Forbidden as e:
                    failed_roles.append(f"@{role.name} (quitar)")
                    logger.warning(
                        f"No se pudo quitar rol {role.name} ({role_id}): {e}. "
                        f"Verifica que el bot tenga permiso 'Gestionar roles' y que "
                        f"su rol este por encima de @{role.name} en la jerarquia."
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

        # Actualizar o eliminar mensaje de moderacion
        if request.mod_message_id:
            mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
            delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
            if mod_channel_id:
                mod_channel = interaction.guild.get_channel(mod_channel_id)
                if mod_channel and isinstance(mod_channel, discord.TextChannel):
                    try:
                        mod_message = await mod_channel.fetch_message(request.mod_message_id)
                        if delete_messages:
                            await mod_message.delete()
                        else:
                            current_content = mod_message.content
                            pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
                            approved_status = format_message(
                                template=config.get(ConfigKey.STATUS_APPROVED),
                                moderator=interaction.user.name,
                            )
                            if pending_status and pending_status in current_content:
                                new_content = current_content.replace(
                                    pending_status, approved_status
                                )
                            else:
                                new_content = current_content + f"\n\n{approved_status}"
                            await mod_message.edit(content=new_content, view=None)
                    except discord.NotFound:
                        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")

        await session.commit()

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_APPROVED_CONFIRMATION)
            or "Verificacion aprobada para {username}.",
            username=request.username,
        )
        if failed_roles:
            roles_warning = ", ".join(failed_roles)
            await interaction.followup.send(
                f"{confirmation}\n\n"
                f"⚠️ **Advertencia:** No se pudieron modificar algunos roles: {roles_warning}\n"
                f"Verifica que:\n"
                f"• El bot tenga el permiso **Gestionar roles**\n"
                f"• El rol del bot este **por encima** de estos roles en la jerarquia",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(confirmation, ephemeral=True)


async def show_rejection_select(
    cog: "VerificationCog",
    interaction: discord.Interaction,
    request_id: int,
) -> None:
    """Mostrar selector de motivos de rechazo.

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interaccion del moderador.
        request_id (int): ID de la solicitud.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    guild_id = interaction.guild.id

    # Verificar si el cog esta habilitado
    if not await cog._is_cog_enabled(guild_id):
        return

    # Obtener toda la configuracion de una vez
    config = await cog._get_all_config(guild_id)

    # Verificar permisos antes de mostrar el selector
    if not has_any_role(member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []):
        await interaction.response.send_message(
            content="No tienes permisos para rechazar verificaciones.",
            ephemeral=True,
        )
        return

    # Verificar que la solicitud existe y pertenece a este guild
    async with cog.bot.database.session() as session:
        verification_service = VerificationService(session=session)
        request = await verification_service.get_request(request_id=request_id)

        if not request or request.guild_id != guild_id:
            not_found_msg = (
                config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE) or "Solicitud no encontrada."
            )
            await interaction.response.send_message(content=not_found_msg, ephemeral=True)
            return

    # Obtener motivos predefinidos configurados
    reasons: list[str] = []
    rejection_reason_keys = [
        ConfigKey.REJECTION_REASON_1,
        ConfigKey.REJECTION_REASON_2,
        ConfigKey.REJECTION_REASON_3,
        ConfigKey.REJECTION_REASON_4,
    ]
    for key in rejection_reason_keys:
        reason = config.get(key) or ""
        if reason and reason.strip():
            reasons.append(reason)

    # Si no hay motivos configurados, usar por defecto
    if not reasons:
        reasons = [
            "Capturas incorrectas o ilegibles",
            "Nombre de usuario no coincide",
            "Informacion insuficiente",
        ]

    # Obtener textos configurables
    select_message = (
        config.get(ConfigKey.REJECTION_SELECT_MESSAGE) or "Selecciona el motivo de rechazo:"
    )
    placeholder = (
        config.get(ConfigKey.REJECTION_SELECT_PLACEHOLDER) or "Selecciona el motivo de rechazo..."
    )
    other_label = config.get(ConfigKey.REJECTION_OTHER_LABEL) or "Otro motivo..."
    other_description = (
        config.get(ConfigKey.REJECTION_OTHER_DESCRIPTION) or "Escribir un motivo personalizado"
    )
    modal_title = config.get(ConfigKey.REJECTION_MODAL_TITLE) or "Motivo de Rechazo"
    modal_label = config.get(ConfigKey.REJECTION_MODAL_LABEL) or "Motivo"
    modal_placeholder = (
        config.get(ConfigKey.REJECTION_MODAL_PLACEHOLDER)
        or "Explica por que se rechaza la verificacion..."
    )

    view = RejectionReasonView(
        request_id=request_id,
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
    cog: "VerificationCog",
    interaction: discord.Interaction,
    request_id: int,
    reason: str,
) -> None:
    """Manejar rechazo de verificacion.

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interaccion del moderador.
        request_id (int): ID de la solicitud.
        reason (str): Motivo del rechazo.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    async with cog.bot.database.session() as session:
        ctx = await validate_mod_action(
            cog=cog,
            interaction=interaction,
            request_id=request_id,
            session=session,
            permission_error_key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
            permission_error_default="No tienes permisos para rechazar verificaciones.",
        )
        if not ctx:
            return

        config, request, verification_service = ctx

        await verification_service.reject(
            request_id=request_id,
            reviewer_id=interaction.user.id,
            reviewer_username=interaction.user.name,
            reason=reason,
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

        # Actualizar o eliminar mensaje de moderacion
        if request.mod_message_id:
            mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
            delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
            if mod_channel_id:
                mod_channel = interaction.guild.get_channel(mod_channel_id)
                if mod_channel and isinstance(mod_channel, discord.TextChannel):
                    try:
                        mod_message = await mod_channel.fetch_message(request.mod_message_id)
                        if delete_messages:
                            await mod_message.delete()
                        else:
                            current_content = mod_message.content
                            pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
                            rejected_status = format_message(
                                template=config.get(ConfigKey.STATUS_REJECTED),
                                moderator=interaction.user.name,
                                reason=reason,
                            )
                            if pending_status and pending_status in current_content:
                                new_content = current_content.replace(
                                    pending_status, rejected_status
                                )
                            else:
                                new_content = current_content + f"\n\n{rejected_status}"
                            await mod_message.edit(content=new_content, view=None)
                    except discord.NotFound:
                        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")

        await session.commit()

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_REJECTED_CONFIRMATION)
            or "Verificacion rechazada para {username}.",
            username=request.username,
        )
        await interaction.followup.send(content=confirmation, ephemeral=True)
