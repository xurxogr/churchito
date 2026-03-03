"""Tests para discord_bot/verification/formatters.py."""

from typing import Any

import discord

from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    _parse_hex_color,
    create_mod_embeds,
    create_panel_embed,
    format_message,
    get_verification_type_display,
)


class TestFormatMessage:
    """Tests para format_message."""

    def test_format_all_placeholders(self) -> None:
        """Probar reemplazo de todos los placeholders."""
        template = "Usuario: {username}, Servidor: {server_name}"

        result = format_message(
            template,
            username="TestUser",
            server_name="TestServer",
        )

        assert result == "Usuario: TestUser, Servidor: TestServer"

    def test_format_empty_placeholders(self) -> None:
        """Probar con placeholder pasado como None."""
        template = "Usuario: {username}"
        result = format_message(template, username=None)
        assert result == "Usuario: "

    def test_format_unmatched_placeholder(self) -> None:
        """Probar que placeholders no pasados se mantienen."""
        template = "Usuario: {username}"
        result = format_message(template)
        assert result == "Usuario: {username}"

    def test_format_no_placeholders(self) -> None:
        """Probar mensaje sin placeholders."""
        template = "Mensaje simple sin placeholders"
        result = format_message(template)
        assert result == template

    def test_format_none_template(self) -> None:
        """Probar con template None."""
        result = format_message(None, username="Test")
        assert result == ""

    def test_format_multiple_same_placeholder(self) -> None:
        """Probar que se reemplazan multiples ocurrencias del mismo placeholder."""
        template = "{username} saluda a {username}"
        result = format_message(template, username="Juan")
        assert result == "Juan saluda a Juan"

    def test_format_with_special_characters(self) -> None:
        """Probar con caracteres especiales en el valor."""
        template = "Usuario: {username}"
        result = format_message(template, username="Test<>User")
        assert result == "Usuario: Test<>User"


class TestCreatePanelEmbed:
    """Tests para create_panel_embed."""

    def test_no_image_url(self) -> None:
        """Probar texto sin URL de imagen devuelve embed con descripción."""
        text = "Mensaje simple sin imagen"
        embed = create_panel_embed(text)

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert embed.description == text

    def test_with_png_image(self) -> None:
        """Probar texto con URL de imagen PNG."""
        text = "Bienvenido al servidor\nhttps://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "image.png" not in (embed.description or "")
        assert "Bienvenido" in (embed.description or "")
        assert embed.image is not None

    def test_with_jpg_image(self) -> None:
        """Probar texto con URL de imagen JPG."""
        text = "Texto con imagen https://example.com/photo.jpg aqui"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "photo.jpg" not in (embed.description or "")
        assert embed.image is not None

    def test_with_jpeg_image(self) -> None:
        """Probar texto con URL de imagen JPEG."""
        text = "https://example.com/photo.jpeg"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_gif_image(self) -> None:
        """Probar texto con URL de imagen GIF."""
        text = "Animacion: https://example.com/animation.gif"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_webp_image(self) -> None:
        """Probar texto con URL de imagen WEBP."""
        text = "Imagen moderna: https://example.com/image.webp"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_query_params(self) -> None:
        """Probar URL de imagen con parametros de query."""
        text = "Imagen: https://example.com/image.png?width=100&height=200"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "width=100" not in (embed.description or "")
        assert embed.image is not None

    def test_removes_extra_newlines(self) -> None:
        """Probar que elimina lineas vacias extra."""
        text = "Primera linea\n\n\nhttps://example.com/image.png\n\n\nUltima linea"
        embed = create_panel_embed(text)

        assert embed is not None
        # No debe haber mas de 2 saltos de linea consecutivos
        assert "\n\n\n" not in (embed.description or "")

    def test_embed_has_blurple_color(self) -> None:
        """Probar que el embed tiene color blurple."""
        text = "Texto https://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.color == discord.Color.blurple()

    def test_embed_description_contains_text(self) -> None:
        """Probar que el embed contiene el texto en la descripcion."""
        text = "Contenido del mensaje https://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "Contenido del mensaje" in (embed.description or "")

    def test_case_insensitive_extension(self) -> None:
        """Probar que la extension es case insensitive."""
        text = "Imagen: https://example.com/image.PNG"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None


class TestGetVerificationTypeDisplay:
    """Tests para get_verification_type_display."""

    def test_regular_type_with_config(self) -> None:
        """Probar tipo regular con config."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Miembro",
        }

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Miembro"

    def test_regular_type_default(self) -> None:
        """Probar tipo regular con valor por defecto."""
        config: dict[str, Any] = {}

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Normal"

    def test_ally_type_with_config(self) -> None:
        """Probar tipo aliado con config."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "Amigo",
        }

        result = get_verification_type_display(VerificationType.ALLY, config)

        assert result == "Amigo"

    def test_ally_type_default(self) -> None:
        """Probar tipo aliado con valor por defecto."""
        config: dict[str, Any] = {}

        result = get_verification_type_display(VerificationType.ALLY, config)

        assert result == "Aliado"

    def test_regular_type_with_none_value(self) -> None:
        """Probar tipo regular cuando config tiene None."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: None,
        }

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Normal"

    def test_ally_type_with_empty_string(self) -> None:
        """Probar tipo aliado cuando config tiene string vacio."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "",
        }

        result = get_verification_type_display(VerificationType.ALLY, config)

        # Empty string is falsy, so it should return default
        assert result == "Aliado"


class TestParseHexColor:
    """Tests para _parse_hex_color."""

    def test_valid_hex_with_hash(self) -> None:
        """Probar color hex válido con #."""
        result = _parse_hex_color("#FF5733")
        assert result is not None
        assert result == discord.Color(0xFF5733)

    def test_valid_hex_without_hash(self) -> None:
        """Probar color hex válido sin #."""
        result = _parse_hex_color("3498db")
        assert result is not None
        assert result == discord.Color(0x3498DB)

    def test_empty_string(self) -> None:
        """Probar con string vacío."""
        result = _parse_hex_color("")
        assert result is None

    def test_none_value(self) -> None:
        """Probar con None."""
        result = _parse_hex_color(None)
        assert result is None

    def test_invalid_length(self) -> None:
        """Probar con longitud inválida."""
        result = _parse_hex_color("#FFF")
        assert result is None

    def test_invalid_characters(self) -> None:
        """Probar con caracteres inválidos."""
        result = _parse_hex_color("#GGGGGG")
        assert result is None

    def test_with_whitespace(self) -> None:
        """Probar que elimina espacios."""
        result = _parse_hex_color("  #FF5733  ")
        assert result is not None
        assert result == discord.Color(0xFF5733)


class TestCreateModEmbeds:
    """Tests para create_mod_embeds."""

    def test_basic_embed_with_default_config(self) -> None:
        """Probar embed básico con configuración por defecto."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            status="Test status",
        )
        assert embeds[0].description is not None
        assert "Test status" in embeds[0].description
        # Default color is #FFA500 (naranja) from DEFAULT_MOD_EMBED_CONFIG
        assert embeds[0].color == discord.Color(0xFFA500)

    def test_with_username_in_footer(self) -> None:
        """Probar embed con username en footer."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
        )
        assert embeds[0].footer is not None
        assert embeds[0].footer.text is not None
        assert "TestUser" in embeds[0].footer.text

    def test_with_user_id_default_thumbnail(self) -> None:
        """Probar embed con thumbnail por defecto basado en user_id."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            user_id=12345,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url is not None
        assert "cdn.discordapp.com" in embeds[0].thumbnail.url

    def test_custom_color_regular(self) -> None:
        """Probar color personalizado para verificación regular."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#3498db",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].color == discord.Color(0x3498DB)

    def test_custom_color_ally(self) -> None:
        """Probar color personalizado para verificación aliado."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "color": "#e74c3c",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].color == discord.Color(0xE74C3C)

    def test_custom_thumbnail_regular(self) -> None:
        """Probar thumbnail personalizado para verificación regular."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "thumbnail_url": "https://example.com/icon.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/icon.png"

    def test_custom_thumbnail_ally(self) -> None:
        """Probar thumbnail personalizado para verificación aliado."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "thumbnail_url": "https://example.com/ally.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/ally.png"

    def test_empty_config_uses_default_color(self) -> None:
        """Probar que configuración vacía usa naranja por defecto."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        # Default color is #FFA500 (naranja) from DEFAULT_MOD_EMBED_CONFIG
        assert embeds[0].color == discord.Color(0xFFA500)

    def test_invalid_color_uses_default(self) -> None:
        """Probar que color inválido usa naranja por defecto."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "invalid",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].color == discord.Color.orange()

    def test_custom_thumbnail_overrides_user_avatar(self) -> None:
        """Probar que thumbnail personalizado tiene prioridad sobre avatar."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "thumbnail_url": "https://example.com/custom.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            user_id=12345,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/custom.png"

    def test_title_regular(self) -> None:
        """Probar título personalizado para verificación regular."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "title": "🟢 Verificación de Miembro",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title == "🟢 Verificación de Miembro"

    def test_title_ally(self) -> None:
        """Probar título personalizado para verificación aliado."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "title": "🟡 Verificación de Aliado",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].title == "🟡 Verificación de Aliado"

    def test_empty_title_not_shown(self) -> None:
        """Probar que título vacío no se muestra."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "title": "",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title is None

    def test_no_title_without_config(self) -> None:
        """Probar que no hay título con configuración por defecto."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title is None

    def test_placeholders_replaced(self) -> None:
        """Probar que los placeholders se reemplazan."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Usuario: {username}, Estado: {status}",
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
            status="Pendiente",
        )
        assert embeds[0].description is not None
        assert "TestUser" in embeds[0].description
        assert "Pendiente" in embeds[0].description

    def test_additional_content_appended(self) -> None:
        """Probar que el contenido adicional se añade."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_content="\n\nPlayer Info: Level 25",
        )
        assert embeds[0].description is not None
        assert "Base content" in embeds[0].description
        assert "Player Info: Level 25" in embeds[0].description

    def test_additional_sections_text(self) -> None:
        """Probar que las secciones adicionales de texto se añaden como campos."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        additional_sections = [
            {"type": "text", "title": "Player Info", "content": "Name: {name}, Level: {level}"},
        ]
        sections_context = {"name": "TestPlayer", "level": "25"}

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )

        assert embeds[0].description is not None
        assert "Base content" in embeds[0].description
        # TEXT section is now a field
        assert len(embeds[0].fields) == 1
        assert embeds[0].fields[0].name == "Player Info"
        assert embeds[0].fields[0].value is not None
        assert "TestPlayer" in embeds[0].fields[0].value
        assert "25" in embeds[0].fields[0].value

    def test_additional_sections_fields(self) -> None:
        """Probar que las secciones adicionales con campos se añaden."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        additional_sections = [
            {
                "type": "fields",
                "inline": True,
                "field_1_name": "Name",
                "field_1_value": "{name}",
                "field_2_name": "Level",
                "field_2_value": "{level}",
                "field_3_name": "Faction",
                "field_3_value": "{faction}",
            },
        ]
        sections_context = {"name": "TestPlayer", "level": "25", "faction": "colonial"}

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )

        assert len(embeds[0].fields) == 3
        assert embeds[0].fields[0].name == "Name"
        assert embeds[0].fields[0].value == "TestPlayer"
        assert embeds[0].fields[1].name == "Level"
        assert embeds[0].fields[1].value == "25"
        assert embeds[0].fields[2].name == "Faction"
        assert embeds[0].fields[2].value == "colonial"

    def test_additional_sections_without_context(self) -> None:
        """Probar secciones adicionales sin contexto (placeholders no resueltos)."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base",
            },
        }
        additional_sections = [
            {"type": "text", "title": "Info", "content": "Name: {name}"},
        ]

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
        )

        # TEXT section is a field, placeholder not resolved stays as-is
        assert len(embeds[0].fields) == 1
        assert embeds[0].fields[0].value is not None
        assert "{name}" in embeds[0].fields[0].value

    def test_mixed_sections_as_fields(self) -> None:
        """Probar que todas las secciones se renderizan como campos."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#FFA500",
                "description": "Main description",
                "sections": [
                    {"type": "text", "title": "Section 1", "content": "Text content"},
                    {
                        "type": "fields",
                        "inline": True,
                        "field_1_name": "Field 1",
                        "field_1_value": "Value 1",
                        "field_2_name": "Field 2",
                        "field_2_value": "Value 2",
                    },
                ],
            },
        }

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
        )

        # Should be single embed
        assert len(embeds) == 1

        # Description from config
        assert embeds[0].description is not None
        assert "Main description" in embeds[0].description

        # All sections are fields
        assert len(embeds[0].fields) == 3
        assert embeds[0].fields[0].name == "Section 1"
        assert embeds[0].fields[0].value == "Text content"
        assert embeds[0].fields[1].name == "Field 1"
        assert embeds[0].fields[2].name == "Field 2"

        # Footer with username
        assert embeds[0].footer is not None
        assert embeds[0].footer.text is not None
        assert "TestUser" in embeds[0].footer.text

    def test_text_sections_as_full_width_fields(self) -> None:
        """Probar que secciones TEXT se renderizan como campos de ancho completo."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [
                    {"type": "text", "title": "Title 1", "content": "Content 1"},
                    {"type": "text", "title": "Title 2", "content": "Content 2"},
                ],
            },
        }

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )

        # All sections as fields in single embed
        assert len(embeds) == 1
        assert len(embeds[0].fields) == 2
        assert embeds[0].fields[0].name == "Title 1"
        assert embeds[0].fields[0].value == "Content 1"
        assert embeds[0].fields[1].name == "Title 2"
        assert embeds[0].fields[1].value == "Content 2"
