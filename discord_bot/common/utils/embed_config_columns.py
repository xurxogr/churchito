"""Definiciones de columnas para tablas de configuración de embeds."""

from typing import Any

from discord_bot.common.enums.embed_section_type import AnsiColor, EmbedSectionType

# Columnas para la tabla de secciones de embed
EMBED_SECTIONS_COLUMNS: list[dict[str, Any]] = [
    {
        "key": "type",
        "name": "Tipo",
        "type": "choice",
        "required": True,
        "choices": [
            ("Texto", EmbedSectionType.TEXT),
            ("Texto con color", EmbedSectionType.TEXT_COLORED),
            ("Encabezado", EmbedSectionType.HEADER),
            ("Barra de progreso", EmbedSectionType.PROGRESS),
            ("Campos (3 columnas)", EmbedSectionType.FIELDS),
        ],
    },
    {
        "key": "content",
        "name": "Contenido",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "description": "Texto para secciones TEXT, TEXT_COLORED y HEADER. Soporta placeholders.",
    },
    # Campos para TEXT_COLORED
    {
        "key": "text_color",
        "name": "Color del texto",
        "type": "choice",
        "required": False,
        "choices": [
            ("Gris", AnsiColor.GRAY),
            ("Rojo", AnsiColor.RED),
            ("Verde", AnsiColor.GREEN),
            ("Amarillo", AnsiColor.YELLOW),
            ("Azul", AnsiColor.BLUE),
            ("Rosa", AnsiColor.PINK),
            ("Cian", AnsiColor.CYAN),
            ("Blanco", AnsiColor.WHITE),
        ],
        "description": "Color ANSI para el texto",
        "show_when": {"type": EmbedSectionType.TEXT_COLORED},
    },
    # Campos para PROGRESS
    {
        "key": "value_key",
        "name": "Placeholder valor",
        "type": "string",
        "required": False,
        "max_length": 50,
        "description": "Nombre del placeholder con el valor numérico (ej: level)",
        "show_when": {"type": EmbedSectionType.PROGRESS},
    },
    {
        "key": "max_value",
        "name": "Valor máximo",
        "type": "integer",
        "required": False,
        "min_value": 1,
        "max_value": 999999,
        "description": "Valor máximo para calcular el porcentaje",
        "show_when": {"type": EmbedSectionType.PROGRESS},
    },
    {
        "key": "label_left",
        "name": "Etiqueta izquierda",
        "type": "string",
        "required": False,
        "max_length": 100,
        "description": "Texto debajo de la barra (izquierda)",
        "show_when": {"type": EmbedSectionType.PROGRESS},
    },
    {
        "key": "label_right",
        "name": "Etiqueta derecha",
        "type": "string",
        "required": False,
        "max_length": 100,
        "description": "Texto debajo de la barra (derecha)",
        "show_when": {"type": EmbedSectionType.PROGRESS},
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
