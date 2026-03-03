"""Servicio para construir embeds configurables con placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.enums.embed_section_type import EmbedSectionType
from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection

if TYPE_CHECKING:
    from discord import Guild, Member


@dataclass
class PlaceholderContext:
    """Contexto con datos para resolver placeholders.

    Los placeholders globales (server_*, user_*) se resuelven automáticamente
    si se proporcionan guild y/o member. Los placeholders adicionales se
    pueden pasar en extra_data.
    """

    guild: Guild | None = None
    member: Member | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)

    def resolve(self, key: str) -> str | None:
        """Resolver un placeholder por su clave.

        Args:
            key: Nombre del placeholder sin llaves.

        Returns:
            Valor resuelto o None si no existe.
        """
        # Primero buscar en extra_data (permite override de globales)
        if key in self.extra_data:
            value = self.extra_data[key]
            return str(value) if value is not None else None

        # Placeholders de servidor
        if self.guild:
            if key == "server_name":
                return self.guild.name
            if key == "server_id":
                return str(self.guild.id)
            if key == "server_member_count":
                return str(self.guild.member_count)

        # Placeholders de usuario
        if self.member:
            if key == "user_name":
                return self.member.display_name
            if key == "user_mention":
                return self.member.mention
            if key == "user_id":
                return str(self.member.id)
            if key == "user_discriminator":
                return self.member.discriminator
            if key == "user_avatar_url":
                return str(self.member.display_avatar.url)
            if key == "user_joined_server":
                if self.member.joined_at:
                    return self.member.joined_at.strftime("%d/%m/%Y %H:%M")
                return "N/A"
            if key == "user_joined_server_relative":
                if self.member.joined_at:
                    return f"<t:{int(self.member.joined_at.timestamp())}:R>"
                return "N/A"
            if key == "user_joined_discord":
                return self.member.created_at.strftime("%d/%m/%Y %H:%M")
            if key == "user_joined_discord_relative":
                return f"<t:{int(self.member.created_at.timestamp())}:R>"

        return None


# Lista de placeholders globales disponibles
GLOBAL_PLACEHOLDERS: list[dict[str, str]] = [
    # Servidor
    {"key": "server_name", "description": "Nombre del servidor"},
    {"key": "server_id", "description": "ID del servidor"},
    {"key": "server_member_count", "description": "Cantidad de miembros"},
    # Usuario
    {"key": "user_name", "description": "Nombre del usuario"},
    {"key": "user_mention", "description": "Mención del usuario"},
    {"key": "user_id", "description": "ID del usuario"},
    {"key": "user_avatar_url", "description": "URL del avatar"},
    {"key": "user_joined_server", "description": "Fecha de entrada al servidor"},
    {"key": "user_joined_server_relative", "description": "Tiempo desde que entró (relativo)"},
    {"key": "user_joined_discord", "description": "Fecha de creación de cuenta"},
    {"key": "user_joined_discord_relative", "description": "Antigüedad de cuenta (relativo)"},
]


def format_placeholders(template: str, context: PlaceholderContext) -> str:
    """Reemplazar placeholders en una plantilla.

    Args:
        template: Texto con placeholders en formato {nombre}.
        context: Contexto con datos para resolver.

    Returns:
        Texto con placeholders reemplazados.
    """
    result = template
    # Encontrar todos los placeholders {xxx}
    import re

    placeholders = re.findall(r"\{(\w+)\}", template)

    for key in placeholders:
        value = context.resolve(key)
        if value is not None:
            result = result.replace(f"{{{key}}}", value)

    # Convert literal \n to actual newlines
    result = result.replace("\\n", "\n")

    return result


def create_progress_bar(
    value: int | float,
    max_value: int | float,
    length: int = 10,
    filled_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Crear una barra de progreso con caracteres Unicode.

    Args:
        value: Valor actual.
        max_value: Valor máximo.
        length: Longitud de la barra en caracteres.
        filled_char: Caracter para la parte llena.
        empty_char: Caracter para la parte vacía.

    Returns:
        Barra de progreso como string.
    """
    if max_value <= 0:
        return empty_char * length

    percentage = min(value / max_value, 1.0)
    filled = int(percentage * length)
    return filled_char * filled + empty_char * (length - filled)


def _parse_hex_color(hex_color: str | None) -> discord.Color | None:
    """Parsear un color hexadecimal a discord.Color."""
    if not hex_color:
        return None
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return discord.Color(int(hex_color, 16))
    except ValueError:
        return None


def _render_section(section: EmbedSection, context: PlaceholderContext) -> dict[str, Any]:
    """Renderizar una sección a datos para el embed.

    Returns:
        Dict con 'fields' (campos a agregar). Todas las secciones ahora son campos.
    """
    # Zero-width space for empty field names/values (Discord requires non-empty)
    EMPTY = "\u200b"
    result: dict[str, Any] = {"fields": []}

    match section.type:
        case EmbedSectionType.TEXT:
            # Full-width field with title + content
            title = format_placeholders(section.title, context) if section.title else EMPTY
            content = format_placeholders(section.content, context) if section.content else EMPTY
            result["fields"].append(
                {
                    "name": title,
                    "value": content,
                    "inline": False,
                }
            )

        case EmbedSectionType.FIELDS:
            # Inline fields (up to 3 per row)
            fields = section.get_fields()
            for field_item in fields:
                result["fields"].append(
                    {
                        "name": format_placeholders(field_item.name, context),
                        "value": format_placeholders(field_item.value, context),
                        "inline": section.inline,
                    }
                )

    return result


class EmbedFieldLimitError(Exception):
    """Error cuando se excede el límite de 25 campos en un embed."""

    def __init__(self, field_count: int) -> None:
        """Inicializar el error.

        Args:
            field_count: Número de campos que se intentaron agregar.
        """
        self.field_count = field_count
        super().__init__(f"El embed excede el límite de 25 campos ({field_count} campos)")


def build_embed(
    config: EmbedConfig,
    context: PlaceholderContext,
    *,
    title: str | None = None,
    default_color: discord.Color | None = None,
    validate_fields: bool = True,
) -> discord.Embed:
    """Construir un embed desde una configuración de secciones.

    Args:
        config: Configuración del embed con secciones.
        context: Contexto con datos para resolver placeholders.
        title: Título opcional (sobrescribe config.title si se proporciona).
        default_color: Color por defecto si no hay color en config.
        validate_fields: Si True, lanza error si se exceden 25 campos.

    Returns:
        discord.Embed construido.

    Raises:
        EmbedFieldLimitError: Si validate_fields=True y se exceden 25 campos.
    """
    # Validar límite de campos
    if validate_fields:
        field_count = config.count_fields()
        if field_count > 25:
            raise EmbedFieldLimitError(field_count)

    # Determinar título (parámetro > config)
    embed_title = title
    if embed_title is None and config.title:
        embed_title = format_placeholders(config.title, context)

    # Determinar color
    color = _parse_hex_color(config.color) or default_color or discord.Color.blurple()

    embed = discord.Embed(title=embed_title, color=color)

    # Descripción (aparece antes de los campos)
    if config.description:
        embed.description = format_placeholders(config.description, context)

    # Construir campos desde secciones (todas las secciones son campos ahora)
    for section in config.sections:
        rendered = _render_section(section, context)
        for field_data in rendered["fields"]:
            embed.add_field(
                name=field_data["name"],
                value=field_data["value"],
                inline=field_data["inline"],
            )

    # Thumbnail
    if config.thumbnail_url:
        url = format_placeholders(config.thumbnail_url, context)
        embed.set_thumbnail(url=url)

    # Imagen principal
    if config.image_url:
        url = format_placeholders(config.image_url, context)
        embed.set_image(url=url)

    # Footer
    if config.footer_text:
        footer_text = format_placeholders(config.footer_text, context)
        footer_icon = None
        if config.footer_icon_url:
            footer_icon = format_placeholders(config.footer_icon_url, context)
        embed.set_footer(text=footer_text, icon_url=footer_icon)

    return embed


def build_embeds(
    config: EmbedConfig,
    context: PlaceholderContext,
    *,
    title: str | None = None,
    default_color: discord.Color | None = None,
) -> list[discord.Embed]:
    """Construir un embed desde una configuración de secciones.

    Todas las secciones se renderizan como campos de Discord. Esta función
    devuelve una lista para mantener compatibilidad con código existente,
    pero siempre devuelve un único embed (ya no hay auto-split).

    Args:
        config: Configuración del embed con secciones.
        context: Contexto con datos para resolver placeholders.
        title: Título opcional (sobrescribe config.title).
        default_color: Color por defecto si no hay color en config.

    Returns:
        Lista con un único discord.Embed construido.
    """
    embed = build_embed(
        config,
        context,
        title=title,
        default_color=default_color,
        validate_fields=False,  # Don't validate here, caller can validate if needed
    )
    return [embed]


def build_embed_from_rows(
    rows: list[dict[str, Any]],
    context: PlaceholderContext,
    *,
    title: str | None = None,
    color: str | None = None,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
    footer_text: str | None = None,
    footer_icon_url: str | None = None,
    default_color: discord.Color | None = None,
    validate_fields: bool = True,
) -> discord.Embed:
    """Construir un embed directamente desde filas de configuración de tabla.

    Atajo para usar con valores de ConfigOptionType.TABLE.

    Args:
        rows: Lista de filas de la tabla de configuración.
        context: Contexto con datos para resolver placeholders.
        title: Título del embed (soporta placeholders).
        color: Color en formato hex.
        thumbnail_url: URL del thumbnail.
        image_url: URL de la imagen principal.
        footer_text: Texto del footer.
        footer_icon_url: URL del icono del footer.
        default_color: Color por defecto si no hay color.
        validate_fields: Si True, lanza error si se exceden 25 campos.

    Returns:
        discord.Embed construido.

    Raises:
        EmbedFieldLimitError: Si validate_fields=True y se exceden 25 campos.
    """
    config = EmbedConfig.from_table_rows(rows)
    config.title = title
    config.color = color
    config.thumbnail_url = thumbnail_url
    config.image_url = image_url
    config.footer_text = footer_text
    config.footer_icon_url = footer_icon_url

    return build_embed(
        config, context, default_color=default_color, validate_fields=validate_fields
    )
