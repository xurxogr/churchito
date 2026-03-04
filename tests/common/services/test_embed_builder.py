"""Tests para el servicio de construcción de embeds."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from discord_bot.common.enums.embed_section_type import EmbedSectionType
from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection
from discord_bot.common.services.embed_builder import (
    ANSI_COLORS,
    COLOR_TAGS,
    DOT_EMOJIS,
    GLOBAL_PLACEHOLDERS,
    EmbedFieldLimitError,
    PlaceholderContext,
    build_embed,
    build_embed_from_rows,
    create_progress_bar,
    format_placeholders,
    format_with_colors,
)


class TestCreateProgressBar:
    """Tests para create_progress_bar."""

    def test_empty_bar(self) -> None:
        """Test barra vacía cuando el valor es 0."""
        bar = create_progress_bar(0, 100)
        assert bar == "░░░░░░░░░░"

    def test_full_bar(self) -> None:
        """Test barra llena cuando el valor es máximo."""
        bar = create_progress_bar(100, 100)
        assert bar == "██████████"

    def test_half_bar(self) -> None:
        """Test barra al 50%."""
        bar = create_progress_bar(50, 100)
        assert bar == "█████░░░░░"

    def test_custom_length(self) -> None:
        """Test barra con longitud personalizada."""
        bar = create_progress_bar(50, 100, length=20)
        assert len(bar) == 20
        assert bar.count("█") == 10

    def test_custom_characters(self) -> None:
        """Test barra con caracteres personalizados."""
        bar = create_progress_bar(30, 100, filled_char="▓", empty_char="▒")
        assert "▓" in bar
        assert "▒" in bar

    def test_max_value_zero(self) -> None:
        """Test con valor máximo 0 devuelve barra vacía."""
        bar = create_progress_bar(50, 0)
        assert bar == "░░░░░░░░░░"

    def test_value_exceeds_max(self) -> None:
        """Test que el valor no exceda el 100%."""
        bar = create_progress_bar(150, 100)
        assert bar == "██████████"


class TestPlaceholderContext:
    """Tests para PlaceholderContext."""

    def test_resolve_extra_data(self) -> None:
        """Test resolver placeholder desde extra_data."""
        context = PlaceholderContext(extra_data={"custom_key": "custom_value"})
        assert context.resolve("custom_key") == "custom_value"

    def test_resolve_server_name(self) -> None:
        """Test resolver server_name desde guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Server"
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_name") == "Test Server"

    def test_resolve_server_id(self) -> None:
        """Test resolver server_id desde guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_id") == "123456789"

    def test_resolve_user_name(self) -> None:
        """Test resolver user_name desde member."""
        member = MagicMock(spec=discord.Member)
        member.display_name = "TestUser"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_name") == "TestUser"

    def test_resolve_user_mention(self) -> None:
        """Test resolver user_mention desde member."""
        member = MagicMock(spec=discord.Member)
        member.mention = "<@123456>"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_mention") == "<@123456>"

    def test_resolve_user_joined_server(self) -> None:
        """Test resolver user_joined_server desde member."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server") == "2024-01-15 10:30"

    def test_resolve_user_joined_server_none(self) -> None:
        """Test resolver user_joined_server cuando es None."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = None
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server") == "N/A"

    def test_resolve_unknown_placeholder(self) -> None:
        """Test resolver placeholder desconocido devuelve None."""
        context = PlaceholderContext()
        assert context.resolve("unknown_key") is None

    def test_extra_data_overrides_global(self) -> None:
        """Test que extra_data tiene prioridad sobre globales."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Real Server Name"
        context = PlaceholderContext(guild=guild, extra_data={"server_name": "Custom Name"})
        assert context.resolve("server_name") == "Custom Name"

    def test_resolve_server_member_count(self) -> None:
        """Test resolver server_member_count desde guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.member_count = 150
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_member_count") == "150"

    def test_resolve_user_id(self) -> None:
        """Test resolver user_id desde member."""
        member = MagicMock(spec=discord.Member)
        member.id = 987654321
        context = PlaceholderContext(member=member)
        assert context.resolve("user_id") == "987654321"

    def test_resolve_user_discriminator(self) -> None:
        """Test resolver user_discriminator desde member."""
        member = MagicMock(spec=discord.Member)
        member.discriminator = "1234"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_discriminator") == "1234"

    def test_resolve_user_avatar_url(self) -> None:
        """Test resolver user_avatar_url desde member."""
        member = MagicMock(spec=discord.Member)
        member.display_avatar.url = "https://cdn.discord.com/avatar.png"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_avatar_url") == "https://cdn.discord.com/avatar.png"

    def test_resolve_user_joined_server_relative(self) -> None:
        """Test resolver user_joined_server_relative desde member."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        result = context.resolve("user_joined_server_relative")
        assert result is not None
        assert result.startswith("<t:")
        assert result.endswith(":R>")

    def test_resolve_user_joined_server_relative_none(self) -> None:
        """Test resolver user_joined_server_relative cuando joined_at es None."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = None
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server_relative") == "N/A"

    def test_resolve_user_joined_discord(self) -> None:
        """Test resolver user_joined_discord desde member."""
        member = MagicMock(spec=discord.Member)
        member.created_at = datetime(2020, 6, 1, 15, 0, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_discord") == "2020-06-01 15:00"

    def test_resolve_user_joined_discord_relative(self) -> None:
        """Test resolver user_joined_discord_relative desde member."""
        member = MagicMock(spec=discord.Member)
        member.created_at = datetime(2020, 6, 1, 15, 0, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        result = context.resolve("user_joined_discord_relative")
        assert result is not None
        assert result.startswith("<t:")
        assert result.endswith(":R>")


class TestFormatPlaceholders:
    """Tests para format_placeholders."""

    def test_single_placeholder(self) -> None:
        """Test reemplazar un solo placeholder."""
        context = PlaceholderContext(extra_data={"name": "Juan"})
        result = format_placeholders("Hola {name}!", context)
        assert result == "Hola Juan!"

    def test_multiple_placeholders(self) -> None:
        """Test reemplazar múltiples placeholders."""
        context = PlaceholderContext(extra_data={"name": "Juan", "level": "10"})
        result = format_placeholders("{name} nivel {level}", context)
        assert result == "Juan nivel 10"

    def test_unresolved_placeholder_stays(self) -> None:
        """Test que placeholders no resueltos se mantienen."""
        context = PlaceholderContext(extra_data={"name": "Juan"})
        result = format_placeholders("Hola {name}, tu nivel es {level}", context)
        assert result == "Hola Juan, tu nivel es {level}"

    def test_no_placeholders(self) -> None:
        """Test texto sin placeholders."""
        context = PlaceholderContext()
        result = format_placeholders("Sin placeholders", context)
        assert result == "Sin placeholders"


class TestBuildEmbed:
    """Tests para build_embed."""

    def test_empty_config(self) -> None:
        """Test construir embed con configuración vacía."""
        config = EmbedConfig(sections=[])
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert isinstance(embed, discord.Embed)
        assert embed.description is None or embed.description == ""

    def test_text_section(self) -> None:
        """Test sección de texto simple se renderiza como campo."""
        config = EmbedConfig(
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Title", content="Hello World")
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert len(embed.fields) == 1
        assert embed.fields[0].name == "Title"
        assert embed.fields[0].value == "Hello World"
        assert embed.fields[0].inline is False

    def test_text_section_with_placeholder(self) -> None:
        """Test sección de texto con placeholder."""
        config = EmbedConfig(
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Saludo", content="Hola {name}!")
            ]
        )
        context = PlaceholderContext(extra_data={"name": "Usuario"})
        embed = build_embed(config, context)

        assert len(embed.fields) == 1
        assert embed.fields[0].value == "Hola Usuario!"

    def test_description_field(self) -> None:
        """Test descripción del embed desde config."""
        config = EmbedConfig(
            description="Esta es la descripción con {name}",
            sections=[],
        )
        context = PlaceholderContext(extra_data={"name": "placeholder"})
        embed = build_embed(config, context)

        assert embed.description == "Esta es la descripción con placeholder"

    def test_fields_section(self) -> None:
        """Test sección de campos."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    inline=True,
                    field_1_name="Campo 1",
                    field_1_value="Valor 1",
                    field_2_name="Campo 2",
                    field_2_value="Valor 2",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Campo 1"
        assert embed.fields[0].value == "Valor 1"
        assert embed.fields[0].inline is True
        assert embed.fields[1].name == "Campo 2"

    def test_custom_color(self) -> None:
        """Test color personalizado."""
        config = EmbedConfig(sections=[], color="#FF5733")
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.color == discord.Color(0xFF5733)

    def test_invalid_color_uses_default(self) -> None:
        """Test color inválido usa el por defecto."""
        config = EmbedConfig(sections=[], color="invalid")
        context = PlaceholderContext()
        embed = build_embed(config, context, default_color=discord.Color.red())

        assert embed.color == discord.Color.red()

    def test_invalid_hex_color_value_error(self) -> None:
        """Test color hex con caracteres inválidos que causa ValueError."""
        config = EmbedConfig(sections=[], color="#GGGGGG")
        context = PlaceholderContext()
        embed = build_embed(config, context, default_color=discord.Color.green())

        assert embed.color == discord.Color.green()

    def test_footer(self) -> None:
        """Test footer del embed."""
        config = EmbedConfig(
            sections=[],
            footer_text="Footer con {name}",
        )
        context = PlaceholderContext(extra_data={"name": "placeholder"})
        embed = build_embed(config, context)

        assert embed.footer.text == "Footer con placeholder"

    def test_footer_with_icon(self) -> None:
        """Test footer del embed con icono."""
        config = EmbedConfig(
            sections=[],
            footer_text="Footer",
            footer_icon_url="https://example.com/icon.png",
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.footer.text == "Footer"
        assert embed.footer.icon_url == "https://example.com/icon.png"

    def test_thumbnail(self) -> None:
        """Test thumbnail del embed."""
        config = EmbedConfig(sections=[], thumbnail_url="https://example.com/image.png")
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.thumbnail.url == "https://example.com/image.png"

    def test_multiple_sections(self) -> None:
        """Test múltiples secciones se renderizan como campos."""
        config = EmbedConfig(
            description="Descripción principal",
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Intro", content="Bienvenido"),
                EmbedSection(type=EmbedSectionType.TEXT, title="Info", content="Más datos"),
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    field_1_name="Campo 1",
                    field_1_value="Valor 1",
                ),
            ],
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.description == "Descripción principal"
        assert len(embed.fields) == 3
        assert embed.fields[0].name == "Intro"
        assert embed.fields[0].value == "Bienvenido"
        assert embed.fields[1].name == "Info"
        assert embed.fields[2].name == "Campo 1"

    def test_title_from_config(self) -> None:
        """Test título desde la configuración."""
        config = EmbedConfig(
            title="Hola {user_name}",
            sections=[],
        )
        context = PlaceholderContext(extra_data={"user_name": "Juan"})
        embed = build_embed(config, context)

        assert embed.title == "Hola Juan"

    def test_title_parameter_overrides_config(self) -> None:
        """Test que el parámetro title tiene prioridad sobre config."""
        config = EmbedConfig(
            title="Título de config",
            sections=[],
        )
        context = PlaceholderContext()
        embed = build_embed(config, context, title="Título de parámetro")

        assert embed.title == "Título de parámetro"

    def test_image_url(self) -> None:
        """Test imagen principal del embed."""
        config = EmbedConfig(
            sections=[],
            image_url="https://example.com/main-image.png",
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.image.url == "https://example.com/main-image.png"

    def test_field_limit_validation_passes(self) -> None:
        """Test que la validación pasa con 25 campos o menos."""
        # 8 secciones FIELDS x 3 campos = 24 campos (dentro del límite)
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(8)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        # No debe lanzar excepción
        embed = build_embed(config, context)
        assert len(embed.fields) == 24

    def test_field_limit_validation_fails(self) -> None:
        """Test que la validación falla con más de 25 campos."""
        # 9 secciones FIELDS x 3 campos = 27 campos (excede el límite)
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(9)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        with pytest.raises(EmbedFieldLimitError) as exc_info:
            build_embed(config, context)

        assert exc_info.value.field_count == 27

    def test_field_limit_validation_disabled(self) -> None:
        """Test que se puede desactivar la validación de campos."""
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(9)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        # No debe lanzar excepción con validate_fields=False
        embed = build_embed(config, context, validate_fields=False)
        assert len(embed.fields) == 27


class TestBuildEmbedFromRows:
    """Tests para build_embed_from_rows."""

    def test_from_table_rows(self) -> None:
        """Test construir embed desde filas de tabla."""
        rows: list[dict[str, Any]] = [
            {"type": "text", "title": "Bienvenida", "content": "Bienvenido {user_name}!"},
            {
                "type": "fields",
                "inline": True,
                "field_1_name": "Servidor",
                "field_1_value": "{server_name}",
            },
        ]

        guild = MagicMock(spec=discord.Guild)
        guild.name = "Mi Servidor"

        member = MagicMock(spec=discord.Member)
        member.display_name = "TestUser"

        context = PlaceholderContext(guild=guild, member=member)
        embed = build_embed_from_rows(rows, context, color="#00FF00", footer_text="Pie de página")

        # TEXT section becomes a field
        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Bienvenida"
        assert embed.fields[0].value == "Bienvenido TestUser!"
        # FIELDS section
        assert embed.fields[1].value == "Mi Servidor"
        assert embed.color == discord.Color(0x00FF00)
        assert embed.footer.text == "Pie de página"


class TestGlobalPlaceholders:
    """Tests para la lista de placeholders globales."""

    def test_global_placeholders_not_empty(self) -> None:
        """Test que la lista de placeholders globales no está vacía."""
        assert len(GLOBAL_PLACEHOLDERS) > 0

    def test_global_placeholders_have_required_keys(self) -> None:
        """Test que todos los placeholders tienen key y description."""
        for placeholder in GLOBAL_PLACEHOLDERS:
            assert "key" in placeholder
            assert "description" in placeholder

    def test_server_placeholders_exist(self) -> None:
        """Test que existen placeholders de servidor."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "server_name" in keys
        assert "server_id" in keys

    def test_user_placeholders_exist(self) -> None:
        """Test que existen placeholders de usuario."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "user_name" in keys
        assert "user_mention" in keys
        assert "user_joined_server" in keys

    def test_dot_emoji_placeholders_exist(self) -> None:
        """Test que existen placeholders de emojis de puntos."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "dot_red" in keys
        assert "dot_green" in keys
        assert "dot_yellow" in keys
        assert "dot_blue" in keys


class TestDotEmojiPlaceholders:
    """Tests para placeholders de emojis de puntos de colores."""

    def test_dot_emojis_mapping(self) -> None:
        """Test que el mapeo de emojis está completo."""
        assert DOT_EMOJIS["dot_red"] == "🔴"
        assert DOT_EMOJIS["dot_green"] == "🟢"
        assert DOT_EMOJIS["dot_yellow"] == "🟡"
        assert DOT_EMOJIS["dot_blue"] == "🔵"
        assert DOT_EMOJIS["dot_white"] == "⚪"
        assert DOT_EMOJIS["dot_black"] == "⚫"
        assert DOT_EMOJIS["dot_orange"] == "🟠"
        assert DOT_EMOJIS["dot_purple"] == "🟣"
        assert DOT_EMOJIS["dot_brown"] == "🟤"

    def test_resolve_dot_red(self) -> None:
        """Test resolver dot_red placeholder."""
        context = PlaceholderContext()
        assert context.resolve("dot_red") == "🔴"

    def test_resolve_dot_green(self) -> None:
        """Test resolver dot_green placeholder."""
        context = PlaceholderContext()
        assert context.resolve("dot_green") == "🟢"

    def test_format_with_dot_emojis(self) -> None:
        """Test usar dot emojis en plantillas."""
        context = PlaceholderContext()
        result = format_placeholders("{dot_green} Online {dot_red} Offline", context)
        assert result == "🟢 Online 🔴 Offline"

    def test_dot_emojis_in_embed_field(self) -> None:
        """Test usar dot emojis en campos de embed."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="Status",
                    content="{dot_green} Active",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value == "🟢 Active"


class TestAnsiColors:
    """Tests para soporte de colores ANSI en texto."""

    def test_ansi_colors_mapping(self) -> None:
        """Test que el mapeo de colores ANSI está completo."""
        assert "red" in ANSI_COLORS
        assert "green" in ANSI_COLORS
        assert "yellow" in ANSI_COLORS
        assert "blue" in ANSI_COLORS
        assert "pink" in ANSI_COLORS
        assert "cyan" in ANSI_COLORS
        assert "white" in ANSI_COLORS
        assert "gray" in ANSI_COLORS

    def test_color_tags_documentation(self) -> None:
        """Test que la documentación de color tags existe."""
        assert len(COLOR_TAGS) > 0
        for tag_info in COLOR_TAGS:
            assert "tag" in tag_info
            assert "description" in tag_info

    def test_format_with_colors_no_colors(self) -> None:
        """Test que texto sin colores no se modifica."""
        context = PlaceholderContext(extra_data={"name": "Test"})
        result = format_with_colors("Hello {name}!", context)
        assert result == "Hello Test!"
        assert "```ansi" not in result

    def test_format_with_colors_single_color(self) -> None:
        """Test que texto con un color se envuelve en bloque ANSI."""
        context = PlaceholderContext()
        result = format_with_colors("{red}Error{/red}", context)
        assert "```ansi" in result
        assert "\u001b[2;31m" in result  # Red ANSI code
        assert "\u001b[0m" in result  # Reset code

    def test_format_with_colors_multiple_colors(self) -> None:
        """Test que texto con múltiples colores funciona."""
        context = PlaceholderContext()
        result = format_with_colors("{green}OK{/green} - {red}Error{/red}", context)
        assert "```ansi" in result
        assert "\u001b[2;32m" in result  # Green
        assert "\u001b[2;31m" in result  # Red

    def test_format_with_colors_and_placeholders(self) -> None:
        """Test combinar colores con placeholders."""
        context = PlaceholderContext(extra_data={"status": "Active"})
        result = format_with_colors("{green}{status}{/green}", context)
        assert "```ansi" in result
        assert "Active" in result

    def test_ansi_colors_in_embed_field(self) -> None:
        """Test usar colores ANSI en campos de embed."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="Status",
                    content="{green}Online{/green}",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value is not None
        assert "```ansi" in embed.fields[0].value
        assert "\u001b[2;32m" in embed.fields[0].value

    def test_field_name_does_not_use_ansi(self) -> None:
        """Test que los nombres de campo no usan ANSI (quedaría feo)."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="{red}Title{/red}",
                    content="Normal content",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        # Field name should NOT have ANSI code block
        assert embed.fields[0].name is not None
        assert "```ansi" not in embed.fields[0].name
        # But the tags remain unprocessed in name
        assert "{red}" in embed.fields[0].name

    def test_inline_fields_support_ansi(self) -> None:
        """Test que campos inline soportan colores ANSI."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    inline=True,
                    field_1_name="Status",
                    field_1_value="{green}OK{/green}",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value is not None
        assert "```ansi" in embed.fields[0].value
