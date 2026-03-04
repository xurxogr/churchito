"""Funciones de formateo para el cog de verificacion."""

from __future__ import annotations

import re
from typing import Any

import discord

from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection
from discord_bot.common.services.embed_builder import (
    PlaceholderContext,
    build_embeds,
)
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType

# Embed config por defecto para moderación
DEFAULT_MOD_EMBED_CONFIG: dict[str, Any] = {
    "color": "#FFA500",
    "description": (
        "**Usuario:** {user_mention} ({username})\n"
        "**Tipo:** {verification_type}\n"
        "**Fecha:** {created_at}\n\n"
        "{status}"
    ),
    "sections": [],
}


def format_message(template: str | None = None, **kwargs: str | None) -> str:
    """Reemplazar placeholders en un mensaje.

    Args:
        template (str | None): Plantilla del mensaje.
        **kwargs: Placeholders a reemplazar (ej: username="Juan", status="Pendiente").

    Returns:
        str: Mensaje formateado.
    """
    result = template or ""
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value or "")
    return result


def create_panel_embed(text: str) -> discord.Embed:
    """Crear un embed para el panel de verificación.

    Busca URLs de imagen en el texto y las usa para el embed.
    La URL de imagen se elimina del texto mostrado.

    Args:
        text (str): Texto del mensaje que puede contener URLs de imagen.

    Returns:
        discord.Embed: Embed con el mensaje formateado.
    """
    # Buscar URLs de imagen
    image_pattern = r"(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s]*)?)"
    match = re.search(pattern=image_pattern, string=text, flags=re.IGNORECASE)

    image_url = None
    clean_text = text

    if match:
        image_url = match.group(1)
        # Eliminar la URL del texto (y lineas vacías extra)
        clean_text = re.sub(
            pattern=image_pattern, repl="", string=text, count=1, flags=re.IGNORECASE
        )
        clean_text = re.sub(pattern=r"\n{3,}", repl="\n\n", string=clean_text).strip()

    embed = discord.Embed(
        description=clean_text,
        color=discord.Color.blurple(),
    )

    if image_url:
        embed.set_image(url=image_url)

    return embed


def _parse_hex_color(hex_color: str | None) -> discord.Color | None:
    """Parsear un color hexadecimal a discord.Color.

    Args:
        hex_color: Color en formato hex (#FF5733 o FF5733).

    Returns:
        discord.Color o None si el formato es inválido.
    """
    if not hex_color:
        return None
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return discord.Color(int(hex_color, 16))
    except ValueError:
        return None


def build_history_section(
    past_requests: list[Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Build history section for mod embeds.

    Args:
        past_requests: List of past verification requests (excluding current).
        config: Cog configuration.

    Returns:
        Section dict for embed, or None if no history.
    """
    if not past_requests:
        return None

    history_label = config.get(ConfigKey.HISTORY_LABEL) or "Historial"
    history_lines = []

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
        line = f"{status_emoji} {past_type_display} - {moderator} ({date_str})"
        if past.rejection_reason:
            line += f" - {past.rejection_reason}"
        history_lines.append(line)

    return {
        "type": "text",
        "title": history_label,
        "content": "\n".join(history_lines),
    }


def build_mod_embed_sections(
    config: dict[str, Any],
    player_info: dict[str, Any] | None,
    past_requests: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Build additional sections and context for mod embeds.

    Args:
        config: Cog configuration.
        player_info: OCR player info dict (from DB or API result).
        past_requests: List of past verification requests (excluding current).

    Returns:
        Tuple of (additional_sections, sections_context).
    """
    additional_sections: list[dict[str, Any]] = []
    sections_context: dict[str, Any] | None = None

    # Add player info sections if available
    if player_info:
        player_info_sections = config.get(ConfigKey.PLAYER_INFO_SECTIONS)
        if player_info_sections and isinstance(player_info_sections, list):
            additional_sections = list(player_info_sections)
            sections_context = player_info

    # Add history section
    history_section = build_history_section(
        past_requests=past_requests,
        config=config,
    )
    if history_section:
        additional_sections.append(history_section)

    return additional_sections, sections_context


def create_mod_embeds(
    verification_type: VerificationType,
    config: dict[str, Any],
    *,
    username: str | None = None,
    user_mention: str | None = None,
    user_id: int | None = None,
    status: str | None = None,
    created_at: str | None = None,
    guild: discord.Guild | None = None,
    member: discord.Member | None = None,
    additional_content: str | None = None,
    additional_sections: list[dict[str, Any]] | None = None,
    sections_context: dict[str, Any] | None = None,
    **extra_placeholders: str | None,
) -> list[discord.Embed]:
    """Crear embeds para el mensaje de moderación con auto-split.

    Cuando una sección de descripción sigue a una de campos (o viceversa),
    se crea un nuevo embed automáticamente para mantener el orden visual.

    Args:
        verification_type: Tipo de verificación (REGULAR o ALLY).
        config: Configuración del cog con el embed config.
        username: Nombre del usuario.
        user_mention: Mención del usuario.
        user_id: ID del usuario (para el thumbnail fallback).
        status: Texto del estado actual.
        created_at: Fecha de creación formateada.
        guild: Guild de Discord (para placeholders globales).
        member: Miembro de Discord (para placeholders de usuario).
        additional_content: Contenido adicional (errores API, historial de usuario).
        additional_sections: Secciones adicionales a añadir (player info, etc.).
        sections_context: Contexto de placeholders para las secciones adicionales.
        **extra_placeholders: Placeholders adicionales.

    Returns:
        list[discord.Embed]: Lista de embeds con el mensaje formateado.
    """
    # Obtener el embed config según el tipo de verificación
    if verification_type == VerificationType.REGULAR:
        embed_config_data = config.get(ConfigKey.MOD_EMBED_REGULAR)
    else:
        embed_config_data = config.get(ConfigKey.MOD_EMBED_ALLY)

    # Usar config por defecto si no hay configuración
    if not embed_config_data or not isinstance(embed_config_data, dict):
        embed_config_data = DEFAULT_MOD_EMBED_CONFIG

    # Construir EmbedConfig desde los datos
    embed_config = EmbedConfig(**embed_config_data)

    # Obtener el nombre del tipo de verificación
    type_display = get_verification_type_display(verification_type, config)

    # Crear contexto con todos los placeholders
    extra_data: dict[str, Any] = {
        "username": username or "",
        "user_mention": user_mention or "",
        "verification_type": type_display,
        "status": status or "",
        "created_at": created_at or "",
        **{k: v or "" for k, v in extra_placeholders.items()},
    }

    context = PlaceholderContext(
        guild=guild,
        member=member,
        extra_data=extra_data,
    )

    # Añadir secciones adicionales al embed config si existen
    all_sections = list(embed_config.sections)

    if additional_sections:
        # Crear contexto combinado para las secciones adicionales
        sections_extra_data = dict(extra_data)
        if sections_context:
            sections_extra_data.update(sections_context)

        # Validar y añadir secciones adicionales
        for section_data in additional_sections:
            if not isinstance(section_data, dict):
                continue
            if not section_data.get("type"):
                continue
            try:
                section = EmbedSection(**section_data)
                all_sections.append(section)
            except (TypeError, ValueError):
                continue

        # Actualizar el contexto con los datos de secciones adicionales
        context = PlaceholderContext(
            guild=guild,
            member=member,
            extra_data=sections_extra_data,
        )

    # Construir el EmbedConfig completo con todas las secciones
    full_config = EmbedConfig(
        title=embed_config.title,
        description=embed_config.description,
        color=embed_config.color,
        thumbnail_url=embed_config.thumbnail_url,
        image_url=embed_config.image_url,
        footer_text=embed_config.footer_text,
        footer_icon_url=embed_config.footer_icon_url,
        sections=all_sections,
    )

    # Construir los embeds con auto-split
    embeds = build_embeds(
        full_config,
        context,
        default_color=discord.Color.orange(),
    )

    # Añadir contenido adicional (errores API, historial) al último embed
    if additional_content and embeds:
        last_embed = embeds[-1]
        current_desc = last_embed.description or ""
        last_embed.description = current_desc + additional_content

    # Fallback para thumbnail si no está configurado (primer embed)
    if embeds and not embeds[0].thumbnail.url and user_id:
        embeds[0].set_thumbnail(url=f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png")

    return embeds


def get_verification_type_display(
    verification_type: VerificationType, config: dict[str, Any]
) -> str:
    """Obtener el nombre a mostrar para un tipo de verificacion.

    Args:
        verification_type (VerificationType): Tipo de verificacion.
        config (dict[str, Any]): Configuracion del cog.

    Returns:
        str: Nombre a mostrar.
    """
    if verification_type == VerificationType.REGULAR:
        return config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
    return config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Aliado"


def create_tracker_embed(
    pending_requests: list[Any],
    config: dict[str, Any],
    guild_id: int,
    channel_id: int,
) -> discord.Embed:
    """Crear embed mostrando todas las verificaciones pendientes.

    Agrupa las solicitudes por tipo de verificación y muestra cada una
    en formato compacto: id, username, estado y tiempo relativo.

    Args:
        pending_requests: Lista de VerificationRequest pendientes.
        config: Configuración del cog.
        guild_id: ID del guild para construir links.
        channel_id: ID del canal de moderación para construir links.

    Returns:
        discord.Embed: Embed con la lista de verificaciones pendientes.
    """
    title = config.get(ConfigKey.TRACKER_TITLE) or "📋 Verificaciones Pendientes"
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue(),
    )

    # Group requests by verification type
    grouped: dict[str, list[Any]] = {}
    for request in pending_requests:
        v_type = request.verification_type
        if v_type not in grouped:
            grouped[v_type] = []
        grouped[v_type].append(request)

    sections = []
    for v_type, requests in grouped.items():
        # Get type display name for header
        verification_type = VerificationType(v_type)
        type_display = get_verification_type_display(verification_type, config)

        lines = [f"**{type_display}**"]
        for request in requests:
            # Get status text
            if request.status == VerificationStatus.PENDING_SCREENSHOTS:
                status_text = (
                    config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or "Esperando capturas"
                )
            else:
                status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or "Pendiente de revisión"
            status_text = _clean_status_text(status_text)

            # Timestamp relativo de Discord
            unix_timestamp = int(request.created_at.timestamp())
            relative_time = f"<t:{unix_timestamp}:R>"

            # Link al mensaje de moderación usando ID de verificación
            if request.mod_message_id:
                message_link = (
                    f"https://discord.com/channels/{guild_id}/{channel_id}/{request.mod_message_id}"
                )
                id_text = f"[#{request.id}]({message_link})"
            else:
                id_text = f"#{request.id}"

            # Compact line: id username - status - time
            line = f"{id_text} {request.username} - {status_text} - {relative_time}"
            lines.append(line)

        sections.append("\n".join(lines))

    embed.description = "\n\n".join(sections)
    return embed


def _clean_status_text(status_text: str) -> str:
    """Limpiar texto de estado quitando emojis y formato de negrita.

    Args:
        status_text: Texto de estado desde config (puede incluir emoji y markdown).

    Returns:
        Texto limpio sin emojis iniciales ni formato.
    """
    # Quitar patrones comunes como "⏳ **Estado:** " o "🔍 **Estado:** "
    import re

    # Quitar emoji al inicio
    cleaned = re.sub(r"^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\s]+", "", status_text)
    # Quitar **Estado:** o similar
    cleaned = re.sub(r"\*\*[^*]+:\*\*\s*", "", cleaned)
    return cleaned.strip()
