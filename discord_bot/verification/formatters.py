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


def create_panel_embed(text: str) -> tuple[discord.Embed | None, str]:
    """Crear un embed para el panel de verificacion si hay una imagen.

    Busca URLs de imagen en el texto y las usa para crear un embed.
    La URL de imagen se elimina del texto mostrado.

    Args:
        text (str): Texto del mensaje que puede contener URLs de imagen.

    Returns:
        tuple[discord.Embed | None, str]: Embed (o None) y texto limpio.
    """
    # Buscar URLs de imagen
    image_pattern = r"(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s]*)?)"
    match = re.search(pattern=image_pattern, string=text, flags=re.IGNORECASE)

    if not match:
        return None, text

    image_url = match.group(1)
    # Eliminar la URL del texto (y lineas vacias extra)
    clean_text = re.sub(pattern=image_pattern, repl="", string=text, count=1, flags=re.IGNORECASE)
    clean_text = re.sub(pattern=r"\n{3,}", repl="\n\n", string=clean_text).strip()

    embed = discord.Embed(
        description=clean_text,
        color=discord.Color.blurple(),
    )
    embed.set_image(url=image_url)
    return embed, clean_text


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
