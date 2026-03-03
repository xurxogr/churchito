"""Definiciones de columnas para tablas de configuración de embeds."""

from typing import Any

from discord_bot.common.enums.embed_section_type import EmbedSectionType

# Columnas para la tabla de secciones de embed
EMBED_SECTIONS_COLUMNS: list[dict[str, Any]] = [
    {
        "key": "type",
        "name": "Tipo",
        "type": "choice",
        "required": True,
        "choices": [
            ("Texto", EmbedSectionType.TEXT),
            ("Campos (3 columnas)", EmbedSectionType.FIELDS),
        ],
    },
    # Campos para TEXT
    {
        "key": "title",
        "name": "Título",
        "type": "string",
        "required": False,
        "max_length": 256,
        "description": "Título del campo (se muestra en negrita)",
        "show_when": {"type": EmbedSectionType.TEXT},
    },
    {
        "key": "content",
        "name": "Contenido",
        "type": "textarea",
        "required": False,
        "max_length": 1024,
        "description": "Contenido del campo. Soporta placeholders.",
        "show_when": {"type": EmbedSectionType.TEXT},
    },
    # Campos para FIELDS
    {
        "key": "inline",
        "name": "En línea",
        "type": "boolean",
        "required": False,
        "default": True,
        "description": "Mostrar campos en la misma línea (máximo 3 por fila)",
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_1_name",
        "name": "Campo 1: Nombre",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_1_value",
        "name": "Campo 1: Valor",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_2_name",
        "name": "Campo 2: Nombre",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_2_value",
        "name": "Campo 2: Valor",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_3_name",
        "name": "Campo 3: Nombre",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_3_value",
        "name": "Campo 3: Valor",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
]


def get_embed_sections_columns() -> list[dict[str, Any]]:
    """Obtener las columnas para una tabla de secciones de embed.

    Returns:
        Lista de definiciones de columnas para ConfigOption.columns.
    """
    return EMBED_SECTIONS_COLUMNS.copy()
