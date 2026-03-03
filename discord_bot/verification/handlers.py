"""Manejadores de flujo de verificacion."""

import logging
import re
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import has_any_role
from discord_bot.verification.api_client import (
    VerificationAPIResult,
    call_verification_api,
)
from discord_bot.verification.auto_processor import process_verification
from discord_bot.verification.enums import (
    AutoProcessMode,
    ConfigKey,
    VerificationStatus,
    VerificationType,
)
from discord_bot.verification.formatters import (
    create_mod_embeds,
    format_message,
    get_verification_type_display,
)
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import (
    AutoRejectReviewView,
    ModReviewView,
    RejectionReasonView,
)

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)

# Dominios válidos para URLs de Discord
DISCORD_CDN_DOMAINS = frozenset(
    {
        "cdn.discordapp.com",
        "media.discordapp.net",
    }
)

# API error messages based on status code (422 is handled separately as invalid images)
API_ERROR_MESSAGES: dict[int, str] = {
    401: "API key required or invalid",
    413: "Image exceeds maximum upload size",
    429: "Rate limit exceeded",
    500: "Internal processing error",
}


def _is_valid_discord_url(url: str) -> bool:
    """Verificar que una URL es de Discord CDN.

    Args:
        url (str): URL a verificar

    Returns:
        bool: True si es una URL válida de Discord CDN
    """
    if not url:
        return False

    # Verificar que empieza con https://
    if not url.startswith("https://"):
        return False

    # Extraer dominio
    # URL format: https://domain/path
    domain_part = url[8:]  # Remove "https://"
    domain = domain_part.split("/")[0]
    return domain in DISCORD_CDN_DOMAINS


def _get_api_error_message(status_code: int) -> str:
    """Get human-readable error message for API status code.

    Args:
        status_code: HTTP status code from API

    Returns:
        Error message string
    """
    if status_code in API_ERROR_MESSAGES:
        return API_ERROR_MESSAGES[status_code]
    return f"API Error (code: {status_code})"


def _create_screenshot_embeds(url1: str | None, url2: str | None) -> list[discord.Embed]:
    """Crear embeds para mostrar las capturas de pantalla.

    Crea embeds vacíos con las imágenes para que se muestren
    como miniaturas en una fila en lugar de imágenes grandes apiladas.

    Args:
        url1 (str | None): URL de la primera captura
        url2 (str | None): URL de la segunda captura

    Returns:
        list[discord.Embed]: Lista de embeds con las imágenes
    """
    embeds = []

    if url1:
        embed1 = discord.Embed()
        embed1.set_image(url=url1)
        embeds.append(embed1)

    if url2:
        embed2 = discord.Embed()
        embed2.set_image(url=url2)
        embeds.append(embed2)

    return embeds


def _get_ready_for_approval_status(
    config: dict[str, Any],
    guild: discord.Guild,
) -> str:
    """Obtener el texto de estado 'listo para aprobar' incluyendo roles.

    Args:
        config: Configuración del cog
        guild: Guild para obtener los roles

    Returns:
        Texto del estado formateado
    """
    # Obtener roles de moderador
    mod_role_ids = config.get(ConfigKey.MOD_ROLES) or []
    role_mentions = []

    for role_id in mod_role_ids:
        role = guild.get_role(role_id)
        if role:
            role_mentions.append(role.mention)

    roles_text = ", ".join(role_mentions) if role_mentions else "moderadores"

    # Formatear el estado
    status_template = config.get(ConfigKey.STATUS_READY_FOR_APPROVAL) or ""
    return format_message(status_template, roles=roles_text)


def _try_replace_status(
    content: str,
    template: str,
    new_status: str,
) -> str | None:
    """Intentar reemplazar un estado en el contenido.

    Maneja tanto strings literales como templates con placeholders.

    Args:
        content: Contenido del mensaje
        template: Template del estado a buscar (puede tener placeholders como {roles})
        new_status: Nuevo estado a establecer

    Returns:
        Contenido actualizado si se encontró el estado, None si no
    """
    if not template:
        return None

    # Si el template no tiene placeholders, buscar literal
    if "{" not in template:
        if template in content:
            return content.replace(template, new_status)
        return None

    # Template tiene placeholders - extraer prefijo antes del primer placeholder
    prefix = template.split("{")[0]
    if not prefix:
        return None

    escaped_prefix = re.escape(prefix)
    pattern = escaped_prefix + r"[^\n]*"
    if re.search(pattern, content):
        return re.sub(pattern, new_status, content)

    return None


# Estados que pueden aparecer en un mensaje pendiente (en orden de prioridad)
_PENDING_STATUS_KEYS = (
    ConfigKey.STATUS_AWAITING_SCREENSHOTS,
    ConfigKey.STATUS_PENDING_REVIEW,
    ConfigKey.STATUS_READY_FOR_APPROVAL,
)


def _replace_status_in_content(
    content: str,
    new_status: str,
    config: dict[str, Any],
) -> str:
    """Reemplazar cualquier estado pendiente en el contenido del mensaje.

    Busca y reemplaza cualquier estado de verificación pendiente
    (awaiting screenshots, pending review, ready for approval).

    Args:
        content: Contenido actual del mensaje
        new_status: Nuevo estado a establecer
        config: Configuración del cog

    Returns:
        Contenido con el estado actualizado
    """
    for key in _PENDING_STATUS_KEYS:
        template = config.get(key) or ""
        result = _try_replace_status(content, template, new_status)
        if result is not None:
            return result

    # Si no se encontró ningún estado conocido, añadir al final
    return content + f"\n\n{new_status}"


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

    # Verificar si el usuario ya tiene alguno de los roles de verificacion (miembro o aliado)
    if config.get(ConfigKey.BLOCK_ALREADY_VERIFIED) and isinstance(user, discord.Member):
        regular_roles = config.get(ConfigKey.REGULAR_ROLES_ADD) or []
        ally_roles = config.get(ConfigKey.ALLY_ROLES_ADD) or []
        all_verification_roles = set(regular_roles) | set(ally_roles)

        if all_verification_roles:
            user_role_ids = {role.id for role in user.roles}
            has_any_verification_role = bool(user_role_ids & all_verification_roles)
            if has_any_verification_role:
                await interaction.followup.send(
                    config.get(ConfigKey.ALREADY_VERIFIED_MESSAGE) or "", ephemeral=True
                )
                return

    async with cog.bot.database.session() as session:
        verification_service = VerificationService(session=session)

        # Verificar si tiene verificacion pendiente en este servidor
        pending = await verification_service.get_pending_by_user(guild_id=guild.id, user_id=user.id)
        if pending:
            await interaction.followup.send(
                config.get(ConfigKey.ALREADY_PENDING_MESSAGE) or "", ephemeral=True
            )
            return

        # Verificar si tiene verificacion pendiente en otro servidor
        pending_any = await verification_service.get_any_pending_by_user(user_id=user.id)
        if pending_any:
            await interaction.followup.send(
                config.get(ConfigKey.PENDING_IN_OTHER_SERVER_MESSAGE)
                or "Ya tienes una verificación en curso en otro servidor.",
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
        created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")
        # user es Member en contexto de guild (interaction en guild)
        member = user if isinstance(user, discord.Member) else None
        mod_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=user.name,
            user_mention=user.mention,
            user_id=user.id,
            status=status_text,
            created_at=created_at_str,
            guild=guild,
            member=member,
        )

        mod_message = await mod_channel.send(embeds=mod_embeds)
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

        # Validar que las URLs son de Discord CDN
        url1 = image_attachments[0].url
        url2 = image_attachments[1].url

        if not _is_valid_discord_url(url1) or not _is_valid_discord_url(url2):
            logger.warning(f"URLs de captura inválidas: {url1[:50]}..., {url2[:50]}...")
            formatted = format_message(
                template=config.get(ConfigKey.WRONG_IMAGES_MESSAGE),
                username=message.author.name,
            )
            await message.channel.send(content=formatted)
            return

        del cog._pending_dm_verifications[message.author.id]

        guild = cog.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown"

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

        server_name = guild_name if guild else "el servidor"
        formatted_received = format_message(
            template=config.get(ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE),
            username=message.author.name,
            server_name=server_name,
        )
        await message.channel.send(content=formatted_received)

        # Call verification API if configured (URL and key from global settings)
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
                # 422 is a valid response (invalid images), not an API failure
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
                    await update_mod_message_for_review(
                        cog=cog,
                        channel=mod_channel,
                        request=request,
                        verification_service=verification_service,
                        config=config,
                        api_result=api_result,
                    )

        await session.commit()


async def update_mod_message_for_review(
    cog: "VerificationCog",
    channel: discord.TextChannel,
    request: VerificationRequest,
    verification_service: VerificationService,
    config: dict[str, Any],
    api_result: VerificationAPIResult | None = None,
) -> None:
    """Actualizar mensaje de moderacion cuando se reciben las capturas.

    Args:
        cog (VerificationCog): Instancia del cog.
        channel (discord.TextChannel): Canal de moderacion.
        request (VerificationRequest): Solicitud de verificacion.
        verification_service (VerificationService): Servicio de verificacion.
        config (dict[str, Any]): Configuracion del cog.
        api_result (VerificationAPIResult | None): Resultado de la API de verificación.
    """
    if not request.mod_message_id:
        return

    try:
        mod_message = await channel.fetch_message(request.mod_message_id)
    except discord.NotFound:
        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")
        return

    verification_type = VerificationType(request.verification_type)
    type_display = get_verification_type_display(verification_type=verification_type, config=config)
    status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
    created_at_str = request.created_at.strftime("%Y-%m-%d %H:%M")

    # Build additional content for player info
    additional_content = ""
    additional_sections: list[dict[str, Any]] | None = None
    sections_context: dict[str, Any] | None = None

    if api_result:
        if api_result.success and api_result.response:
            # Get player info sections config
            player_info_sections = config.get(ConfigKey.PLAYER_INFO_SECTIONS)
            if player_info_sections and isinstance(player_info_sections, list):
                additional_sections = player_info_sections
                sections_context = {
                    "name": api_result.response.name or "N/A",
                    "regiment": api_result.response.regiment or "N/A",
                    "level": str(api_result.response.level)
                    if api_result.response.level is not None
                    else "N/A",
                    "faction": api_result.response.faction or "N/A",
                    "shard": api_result.response.shard or "N/A",
                    "time": api_result.response.ingame_time or "N/A",
                    "war": str(api_result.response.war)
                    if api_result.response.war is not None
                    else "N/A",
                    "war_time": api_result.response.current_ingame_time or "N/A",
                }
        elif api_result.status_code == 422:
            # 422 means images are invalid/unreadable - show configured message
            reject_msg = config.get(ConfigKey.REJECT_WRONG_CAPTURES) or "Capturas inválidas"
            additional_content += f"\n\n⚠️ **{reject_msg}**"
        else:
            # Show API error for other status codes
            error_msg = _get_api_error_message(api_result.status_code)
            additional_content += f"\n\n❌ **API Error:** {error_msg}"

    # Crear embeds para las capturas (se muestran en una fila)
    embeds = _create_screenshot_embeds(url1=request.screenshot_1_url, url2=request.screenshot_2_url)

    # Agregar historial
    history = await verification_service.get_user_history(
        guild_id=request.guild_id, user_id=request.user_id
    )
    past_requests = [r for r in history if r.id != request.id]

    if past_requests:
        history_label = config.get(ConfigKey.HISTORY_LABEL) or "Historial"
        additional_content += f"\n\n**{history_label}:**"
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
            additional_content += f"\n{status_emoji} {past_type_display} - {moderator} ({date_str})"
            if past.rejection_reason:
                additional_content += f" - {past.rejection_reason}"

    # Comprobar si debemos auto-procesar
    auto_mode = config.get(ConfigKey.VERIFICATION_AUTOMATIC, AutoProcessMode.NONE)
    # Manejar valores booleanos legacy para compatibilidad
    if auto_mode is True:
        auto_mode = AutoProcessMode.BOTH
    elif auto_mode is False or not auto_mode:
        auto_mode = AutoProcessMode.NONE

    auto_reject = auto_mode in (AutoProcessMode.REJECT_ONLY, AutoProcessMode.BOTH)
    auto_approve = auto_mode in (AutoProcessMode.APPROVE_ONLY, AutoProcessMode.BOTH)

    if (auto_reject or auto_approve) and api_result:
        guild = channel.guild

        # Manejar 422 (imágenes inválidas) - auto-rechazar
        if api_result.status_code == 422 and auto_reject:
            reject_reason = config.get(ConfigKey.REJECT_WRONG_CAPTURES) or "Capturas inválidas"
            await _handle_auto_rejection(
                cog=cog,
                guild=guild,
                request=request,
                verification_service=verification_service,
                config=config,
                mod_message=mod_message,
                additional_content=additional_content,
                embeds=embeds,
                reason=reject_reason,
                additional_sections=additional_sections,
                sections_context=sections_context,
            )
            return

        # Manejar respuesta exitosa de API (200)
        if api_result.success and api_result.response:
            # Obtener nombre de display del miembro para comparación
            member = guild.get_member(request.user_id)
            member_display_name = member.display_name if member else request.username

            # Procesar reglas de verificación
            should_approve, rejection_reason = process_verification(
                request=request,
                api_response=api_result.response,
                config=config,
                member_display_name=member_display_name,
            )

            if should_approve and auto_approve:
                # Auto-aprobar
                await _handle_auto_approval(
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
                return
            elif not should_approve and auto_reject:
                # Auto-rechazar
                await _handle_auto_rejection(
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
                return
            elif should_approve and not auto_approve:
                # Listo para aprobar manualmente - actualizar estado
                # El status_text se actualizará al construir el embed
                status_text = _get_ready_for_approval_status(config=config, guild=guild)

    # Manual review - show buttons
    accept_label = format_message(
        config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Aceptar",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Rechazar"
    view = ModReviewView(
        request_id=request.id, accept_label=accept_label, reject_label=reject_label
    )

    # Crear embeds principales y combinarlos con los embeds de capturas
    member = channel.guild.get_member(request.user_id)
    main_embeds = create_mod_embeds(
        verification_type=verification_type,
        config=config,
        username=request.username,
        user_mention=f"<@{request.user_id}>",
        user_id=request.user_id,
        status=status_text,
        created_at=created_at_str,
        guild=channel.guild,
        member=member,
        additional_content=additional_content,
        additional_sections=additional_sections,
        sections_context=sections_context,
    )
    all_embeds = [*main_embeds, *embeds]
    await mod_message.edit(embeds=all_embeds, view=view)

    # Enviar mensaje de ping a moderadores (las menciones solo funcionan en mensajes nuevos)
    await _send_mod_ping_message(channel=channel, config=config)


async def _send_mod_ping_message(
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

    # Obtener roles de moderador
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


async def _handle_auto_approval(
    cog: "VerificationCog",
    guild: discord.Guild,
    request: VerificationRequest,
    verification_service: VerificationService,
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
    # Approve in database
    await verification_service.approve(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
    )

    # Update member roles
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
                    logger.warning(f"Could not add role {role.name} to {member.name}")

        for role_id in roles_remove or []:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    logger.warning(f"Could not remove role {role.name} from {member.name}")

        # Send approval DM
        approval_msg = format_message(
            template=config.get(approval_msg_key),
            username=request.username,
            server_name=guild.name,
        )
        try:
            await member.send(content=approval_msg)
        except discord.Forbidden:
            pass

    # Update or delete mod message
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
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_id=request.user_id,
            status=approved_status,
            created_at=created_at_str,
            guild=guild,
            member=member,
            additional_content=additional_content,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )
        # Aplicar color verde a todos los embeds principales
        for embed in main_embeds:
            embed.color = discord.Color.green()
        all_embeds = [*main_embeds, *embeds]
        await mod_message.edit(embeds=all_embeds, view=None)


async def _handle_auto_rejection(
    cog: "VerificationCog",
    guild: discord.Guild,
    request: VerificationRequest,
    verification_service: VerificationService,
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
    # Reject in database
    await verification_service.reject(
        request_id=request.id,
        reviewer_id=cog.bot.user.id if cog.bot.user else 0,
        reviewer_username="Auto",
        reason=reason,
    )

    # Send rejection DM
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

    # Actualizar o eliminar mensaje de moderación
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
        main_embeds = create_mod_embeds(
            verification_type=verification_type,
            config=config,
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            user_id=request.user_id,
            status=rejected_status,
            created_at=created_at_str,
            guild=guild,
            member=member,
            additional_content=additional_content,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )
        # Aplicar color rojo a todos los embeds principales
        for embed in main_embeds:
            embed.color = discord.Color.red()
        all_embeds = [*main_embeds, *embeds]

        # Añadir botón de revisión si está configurado
        review_window = config.get(ConfigKey.AUTO_REJECT_REVIEW_WINDOW, 0)
        if review_window and review_window > 0:
            review_label = config.get(ConfigKey.REVIEW_BUTTON_TEXT) or "Revisar"
            view: discord.ui.View | None = AutoRejectReviewView(
                request_id=request.id,
                review_label=review_label,
                timeout_minutes=review_window,
            )
        else:
            view = None

        await mod_message.edit(embeds=all_embeds, view=view)


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
                    logger.warning(f"[{interaction.guild.name}] Rol no encontrado (ID: {role_id})")
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
                    logger.warning(f"[{interaction.guild.name}] Rol no encontrado (ID: {role_id})")
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

        # Actualizar o eliminar mensaje de moderación
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
                            # Obtener contenido del embed principal
                            current_content = ""
                            if mod_message.embeds:
                                current_content = mod_message.embeds[0].description or ""
                            approved_status = format_message(
                                template=config.get(ConfigKey.STATUS_APPROVED),
                                moderator=interaction.user.name,
                            )
                            new_content = _replace_status_in_content(
                                content=current_content,
                                new_status=approved_status,
                                config=config,
                            )
                            # Actualizar el embed existente con el nuevo contenido
                            main_embed = mod_message.embeds[0].copy()
                            main_embed.description = new_content
                            main_embed.color = discord.Color.green()
                            # Mantener embeds de capturas (todos excepto el primero)
                            screenshot_embeds = mod_message.embeds[1:] if mod_message.embeds else []
                            all_embeds = [main_embed, *screenshot_embeds]
                            await mod_message.edit(embeds=all_embeds, view=None)
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
            # For REJECT_WRONG_SHARD, replace {shard} placeholder with configured shard
            if key == ConfigKey.REJECT_WRONG_SHARD:
                expected_shard = config.get(ConfigKey.VERIFICATION_SHARD) or ""
                if expected_shard:
                    reason = reason.replace("{shard}", expected_shard)
                else:
                    continue  # Skip if no shard configured
            reasons.append(reason)

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

        # Actualizar o eliminar mensaje de moderación
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
                            # Obtener contenido del embed principal
                            current_content = ""
                            if mod_message.embeds:
                                current_content = mod_message.embeds[0].description or ""
                            rejected_status = format_message(
                                template=config.get(ConfigKey.STATUS_REJECTED),
                                moderator=interaction.user.name,
                                reason=reason,
                            )
                            new_content = _replace_status_in_content(
                                content=current_content,
                                new_status=rejected_status,
                                config=config,
                            )
                            # Actualizar el embed existente con el nuevo contenido
                            main_embed = mod_message.embeds[0].copy()
                            main_embed.description = new_content
                            main_embed.color = discord.Color.red()
                            # Mantener embeds de capturas (todos excepto el primero)
                            screenshot_embeds = mod_message.embeds[1:] if mod_message.embeds else []
                            all_embeds = [main_embed, *screenshot_embeds]
                            await mod_message.edit(embeds=all_embeds, view=None)
                    except discord.NotFound:
                        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")

        await session.commit()

        confirmation = format_message(
            template=config.get(ConfigKey.MOD_REJECTED_CONFIRMATION)
            or "Verificación rechazada para {username}.",
            username=request.username,
        )
        await interaction.followup.send(content=confirmation, ephemeral=True)


async def handle_review(
    cog: "VerificationCog",
    interaction: discord.Interaction,
    request_id: int,
) -> None:
    """Manejar revisión de una verificación auto-rechazada.

    Permite a los moderadores revisar manualmente una verificación
    que fue auto-rechazada, poniéndola de nuevo en estado pendiente.

    Args:
        cog (VerificationCog): Instancia del cog.
        interaction (discord.Interaction): Interacción del moderador.
        request_id (int): ID de la solicitud.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    if not await cog._is_cog_enabled(interaction.guild.id):
        return

    async with cog.bot.database.session() as session:
        # Validación personalizada para handle_review (permite estado REJECTED)
        config_service = ConfigService(session=session)
        config = await cog._get_all_config(
            guild_id=interaction.guild.id, config_service=config_service
        )

        # Verificar permisos de moderador
        if not has_any_role(
            member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []
        ):
            await interaction.response.send_message(
                content=config.get(ConfigKey.NO_PERMISSION_REJECT_MESSAGE)
                or "No tienes permisos para revisar verificaciones.",
                ephemeral=True,
            )
            return

        verification_service = VerificationService(session=session)
        request = await verification_service.get_request(request_id=request_id)

        if not request or request.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE)
                or "Solicitud no encontrada.",
                ephemeral=True,
            )
            return

        # Verificar que fue auto-rechazada (status debe ser REJECTED y reviewer "Auto")
        if request.status != VerificationStatus.REJECTED or request.reviewed_by_username != "Auto":
            await interaction.response.send_message(
                content="Esta verificación no fue auto-rechazada.",
                ephemeral=True,
            )
            return

        # Verificar que es la última verificación del usuario
        latest = await verification_service.get_latest_by_user(
            guild_id=interaction.guild.id,
            user_id=request.user_id,
        )
        if not latest or latest.id != request_id:
            await interaction.response.send_message(
                content="Solo se puede revisar la última verificación del usuario.",
                ephemeral=True,
            )
            return

        # Revertir a estado pendiente de revisión
        reverted = await verification_service.revert_to_pending_review(request_id)
        if not reverted:
            await interaction.response.send_message(
                content="No se pudo revertir la verificación.",
                ephemeral=True,
            )
            return

        # Actualizar mensaje de moderación con botones de aceptar/rechazar
        await _update_mod_message_for_review(interaction.guild, request, config, request_id)

        await session.commit()

        await interaction.response.send_message(
            content=f"Verificación de {request.username} puesta en revisión manual.",
            ephemeral=True,
        )


async def _update_mod_message_for_review(
    guild: discord.Guild,
    request: VerificationRequest,
    config: dict[str, Any],
    request_id: int,
) -> None:
    """Actualizar mensaje de moderación para revisión manual.

    Args:
        guild: Guild donde está el mensaje
        request: Solicitud de verificación
        config: Configuración del cog
        request_id: ID de la solicitud
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
        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")
        return

    # Obtener contenido actual y actualizar estado
    current_content = ""
    if mod_message.embeds:
        current_content = mod_message.embeds[0].description or ""

    # Reemplazar estado de auto-rechazo por pendiente
    pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "⏳ Pendiente de revisión"
    rejected_status = config.get(ConfigKey.STATUS_REJECTED) or ""

    if rejected_status and rejected_status in current_content:
        new_content = current_content.replace(rejected_status, pending_status)
    else:
        # Si no encuentra el estado, buscar el patrón común
        import re

        pattern = r"❌[^\n]*(?:Auto|rechazo)[^\n]*"
        new_content = re.sub(pattern, pending_status, current_content)
        if new_content == current_content:
            new_content = current_content + f"\n\n{pending_status}"

    # Actualizar el embed existente con el nuevo contenido
    main_embed = mod_message.embeds[0].copy() if mod_message.embeds else discord.Embed()
    main_embed.description = new_content

    # Mantener embeds de capturas
    screenshot_embeds = mod_message.embeds[1:] if mod_message.embeds else []
    all_embeds = [main_embed, *screenshot_embeds]

    # Crear vista con botones de aceptar/rechazar
    type_display = get_verification_type_display(
        verification_type=VerificationType(request.verification_type), config=config
    )
    accept_label = format_message(
        config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Aceptar",
        verification_type=type_display,
    )
    reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Rechazar"
    view = ModReviewView(
        request_id=request_id,
        accept_label=accept_label,
        reject_label=reject_label,
    )

    await mod_message.edit(embeds=all_embeds, view=view)


async def update_mod_message_cancelled(
    guild: discord.Guild,
    request: "VerificationRequest",
    config: dict[str, Any],
) -> None:
    """Actualizar el mensaje de moderación cuando una verificación es cancelada.

    Se usa cuando un usuario sale del servidor mientras tiene una verificación pendiente.

    Args:
        guild: Guild donde está el canal de moderación
        request: Solicitud de verificación cancelada
        config: Configuración del cog
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
        logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")
        return

    if config.get(ConfigKey.DELETE_PROCESSED_MESSAGES):
        await mod_message.delete()
        return

    # Obtener contenido del embed principal
    current_content = ""
    if mod_message.embeds:
        current_content = mod_message.embeds[0].description or ""

    cancelled_status = config.get(ConfigKey.STATUS_CANCELLED) or "🚫 **Estado:** Cancelado"
    new_content = _replace_status_in_content(
        content=current_content,
        new_status=cancelled_status,
        config=config,
    )

    # Actualizar el embed existente con el nuevo contenido y color gris
    main_embed = mod_message.embeds[0].copy() if mod_message.embeds else discord.Embed()
    main_embed.description = new_content
    main_embed.color = discord.Color.dark_grey()

    # Mantener embeds de capturas (todos excepto el primero)
    screenshot_embeds = mod_message.embeds[1:] if mod_message.embeds else []
    all_embeds = [main_embed, *screenshot_embeds]

    await mod_message.edit(embeds=all_embeds, view=None)
