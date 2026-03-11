"""Utilidades para los handlers de verificación."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.formatters import build_mod_embed_sections, format_message

if TYPE_CHECKING:
    from discord_bot.verification.models import VerificationRequest
    from discord_bot.verification.service import VerificationService

# API error messages based on status code (422 is handled separately as invalid images)
API_ERROR_MESSAGES: dict[int, str] = {
    401: "API key required or invalid",
    413: "Image exceeds maximum upload size",
    429: "Rate limit exceeded",
    500: "Internal processing error",
}


def calculate_expires_timestamp(created_at: datetime, timeout_minutes: int) -> str:
    """Calcular el timestamp de expiración para el placeholder {expires}.

    Args:
        created_at: Fecha de creación de la solicitud.
        timeout_minutes: Minutos de timeout configurados.

    Returns:
        Timestamp relativo de Discord (ej: "<t:1234567890:R>") o cadena vacía
        si el timeout está desactivado (0).
    """
    if timeout_minutes <= 0:
        return ""
    expires_at = created_at + timedelta(minutes=timeout_minutes)
    return f"<t:{int(expires_at.timestamp())}:R>"


def get_api_error_message(status_code: int) -> str:
    """Get human-readable error message for API status code.

    Args:
        status_code: HTTP status code from API

    Returns:
        Error message string
    """
    if status_code in API_ERROR_MESSAGES:
        return API_ERROR_MESSAGES[status_code]
    return f"API Error (code: {status_code})"


def create_screenshot_embeds(url1: str | None, url2: str | None) -> list[discord.Embed]:
    """Crear embeds para mostrar las capturas de pantalla.

    Crea embeds con la misma URL base para que Discord los muestre
    como miniaturas en una fila en lugar de imágenes grandes apiladas.

    Args:
        url1: URL de la primera captura
        url2: URL de la segunda captura

    Returns:
        Lista de embeds con las imágenes
    """
    embeds = []
    # Usar una URL común para que Discord muestre las imágenes en fila
    # Esto es un truco de Discord: embeds con la misma url se agrupan visualmente
    common_url = "https://discord.com"

    if url1:
        embed1 = discord.Embed(url=common_url)
        embed1.set_image(url=url1)
        embeds.append(embed1)

    if url2:
        embed2 = discord.Embed(url=common_url)
        embed2.set_image(url=url2)
        embeds.append(embed2)

    return embeds


def get_ready_for_approval_status(
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
    mod_role_ids = config.get(ConfigKey.MOD_ROLES) or []
    role_mentions = []

    for role_id in mod_role_ids:
        role = guild.get_role(role_id)
        if role:
            role_mentions.append(role.mention)

    roles_text = ", ".join(role_mentions) if role_mentions else "moderadores"

    status_template = config.get(ConfigKey.STATUS_READY_FOR_APPROVAL) or ""
    return format_message(status_template, roles=roles_text)


async def get_embed_additional_sections(
    request: "VerificationRequest",
    config: dict[str, Any],
    verification_service: "VerificationService",
    player_info: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Obtener secciones adicionales (player info + historial) para el embed.

    Args:
        request: Solicitud de verificación
        config: Configuración del cog
        verification_service: Servicio de verificación
        player_info: Info del jugador (si None, se lee de request.player_info)

    Returns:
        Tupla de (additional_sections, sections_context)
    """
    if player_info is None:
        player_info = request.player_info

    history = await verification_service.get_user_history(
        guild_id=request.guild_id,
        user_id=request.user_id,
    )
    past_requests = [r for r in history if r.id != request.id]

    return build_mod_embed_sections(
        config=config,
        player_info=player_info,
        past_requests=past_requests,
    )
