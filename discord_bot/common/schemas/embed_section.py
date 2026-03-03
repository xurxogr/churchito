"""Esquemas para secciones de embeds configurables."""

from typing import Any

from pydantic import BaseModel, Field

from discord_bot.common.enums.embed_section_type import EmbedSectionType


class EmbedFieldItem(BaseModel):
    """Definición de un campo dentro de una sección FIELDS."""

    name: str = Field(description="Nombre/título del campo")
    value: str = Field(description="Valor del campo (puede contener placeholders)")


class EmbedSection(BaseModel):
    """Definición de una sección de embed."""

    type: EmbedSectionType = Field(description="Tipo de sección")
    content: str = Field(default="", description="Contenido de texto (para TEXT, HEADER)")

    # Para PROGRESS
    value_key: str | None = Field(default=None, description="Clave del placeholder para el valor")
    max_value: int | None = Field(default=None, description="Valor máximo para la barra")
    label_left: str | None = Field(default=None, description="Etiqueta izquierda")
    label_right: str | None = Field(default=None, description="Etiqueta derecha")

    # Para FIELDS
    inline: bool = Field(default=True, description="Si los campos son inline")
    field_1_name: str | None = Field(default=None, description="Nombre del campo 1")
    field_1_value: str | None = Field(default=None, description="Valor del campo 1")
    field_2_name: str | None = Field(default=None, description="Nombre del campo 2")
    field_2_value: str | None = Field(default=None, description="Valor del campo 2")
    field_3_name: str | None = Field(default=None, description="Nombre del campo 3")
    field_3_value: str | None = Field(default=None, description="Valor del campo 3")

    def get_fields(self) -> list[EmbedFieldItem]:
        """Obtener lista de campos definidos."""
        fields = []
        for i in range(1, 4):
            name = getattr(self, f"field_{i}_name")
            value = getattr(self, f"field_{i}_value")
            if name and value:
                fields.append(EmbedFieldItem(name=name, value=value))
        return fields


class EmbedConfig(BaseModel):
    """Configuración completa de un embed."""

    sections: list[EmbedSection] = Field(default_factory=list)
    color: str | None = Field(default=None, description="Color en formato hex (#FF5733)")
    thumbnail_url: str | None = Field(default=None, description="URL del thumbnail")
    footer_text: str | None = Field(default=None, description="Texto del footer")
    footer_icon_url: str | None = Field(default=None, description="URL del icono del footer")

    @classmethod
    def from_table_rows(cls, rows: list[dict[str, Any]]) -> "EmbedConfig":
        """Crear configuración desde filas de tabla de config."""
        sections = []
        for row in rows:
            section_type = row.get("type", EmbedSectionType.TEXT)
            section = EmbedSection(
                type=section_type,
                content=row.get("content", ""),
                value_key=row.get("value_key"),
                max_value=row.get("max_value"),
                label_left=row.get("label_left"),
                label_right=row.get("label_right"),
                inline=row.get("inline", True),
                field_1_name=row.get("field_1_name"),
                field_1_value=row.get("field_1_value"),
                field_2_name=row.get("field_2_name"),
                field_2_value=row.get("field_2_value"),
                field_3_name=row.get("field_3_name"),
                field_3_value=row.get("field_3_value"),
            )
            sections.append(section)
        return cls(sections=sections)
