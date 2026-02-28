"""Funciones de formateo para el cog de verificacion."""

from __future__ import annotations

import re
from typing import Any

import discord

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.enums import ConfigKey, VerificationType


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


def create_mod_embed(
    text: str,
    username: str | None = None,
    user_id: int | None = None,
) -> discord.Embed:
    """Crear un embed para el mensaje de moderación.

    Args:
        text: Texto del mensaje de moderación.
        username: Nombre del usuario (para el footer).
        user_id: ID del usuario (para el thumbnail).

    Returns:
        discord.Embed: Embed con el mensaje formateado.
    """
    embed = discord.Embed(
        description=text,
        color=discord.Color.orange(),
    )

    if username:
        embed.set_footer(text=f"Usuario: {username}")

    if user_id:
        # Usar el avatar del usuario como thumbnail si está disponible
        embed.set_thumbnail(url=f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png")

    return embed


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


def format_player_info(
    template: str | None,
    api_response: VerificationAPIResponse,
) -> str:
    """Format player info using template and API response.

    Args:
        template: Template with placeholders
        api_response: API response with player data

    Returns:
        Formatted string
    """
    if not template:
        return ""

    return format_message(
        template=template,
        name=api_response.name,
        regiment=api_response.regiment or "N/A",
        level=str(api_response.level),
        faction=api_response.faction,
        shard=api_response.shard,
        time=api_response.ingame_time,
        war=str(api_response.war),
        war_time=api_response.current_ingame_time,
    )
