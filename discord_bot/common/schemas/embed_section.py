"""Schemas for configurable embed sections."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from discord_bot.common.enums.embed_section_type import EmbedSectionType


class EmbedFieldItem(BaseModel):
    """Definition of a field within a FIELDS section."""

    name: str = Field(description="Name/title of the field")
    value: str = Field(description="Value of the field (can contain placeholders)")


class EmbedSection(BaseModel):
    """Definition of an embed section."""

    type: EmbedSectionType = Field(description="Section type")

    # For TEXT
    title: str = Field(default="", description="Title/name of the field")
    content: str = Field(default="", description="Text content")

    # For FIELDS
    inline: bool = Field(default=True, description="Whether fields are inline")
    field_1_name: str | None = Field(default=None, description="Field 1 name")
    field_1_value: str | None = Field(default=None, description="Field 1 value")
    field_2_name: str | None = Field(default=None, description="Field 2 name")
    field_2_value: str | None = Field(default=None, description="Field 2 value")
    field_3_name: str | None = Field(default=None, description="Field 3 name")
    field_3_value: str | None = Field(default=None, description="Field 3 value")

    def get_fields(self) -> list[EmbedFieldItem]:
        """Get list of defined fields."""
        fields = []
        for i in range(1, 4):
            name = getattr(self, f"field_{i}_name")
            value = getattr(self, f"field_{i}_value")
            if name and value:
                fields.append(EmbedFieldItem(name=name, value=value))
        return fields


class EmbedConfig(BaseModel):
    """Complete embed configuration."""

    # Main embed properties
    title: str | None = Field(default=None, description="Embed title")
    description: str | None = Field(
        default=None, description="Embed description (appears before fields)"
    )
    color: str | None = Field(default=None, description="Color in hex format (#FF5733)")

    # Images
    thumbnail_url: str | None = Field(default=None, description="Thumbnail URL (corner)")
    image_url: str | None = Field(default=None, description="Main image URL")

    # Footer
    footer_text: str | None = Field(default=None, description="Footer text")
    footer_icon_url: str | None = Field(default=None, description="Footer icon URL")

    # Sections that make up the embed body
    sections: list[EmbedSection] = Field(default_factory=list)

    def count_fields(self) -> int:
        """Count the total number of fields across all sections."""
        total = 0
        for section in self.sections:
            if section.type == EmbedSectionType.FIELDS:
                total += len(section.get_fields())
            elif section.type == EmbedSectionType.TEXT:
                total += 1
        return total

    def validate_field_limit(self) -> bool:
        """Validate that Discord's 25 field limit is not exceeded.

        Returns:
            True if within limit, False if exceeded.
        """
        return self.count_fields() <= 25

    @classmethod
    def from_table_rows(cls, rows: list[dict[str, Any]]) -> EmbedConfig:
        """Create configuration from config table rows."""
        sections = []
        for row in rows:
            section_type = row.get("type", EmbedSectionType.TEXT)
            section = EmbedSection(
                type=section_type,
                title=row.get("title", ""),
                content=row.get("content", ""),
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
