"""Tests para discord_bot/verification/formatters.py."""

from typing import Any

import discord

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import (
    create_panel_embed,
    format_message,
    format_player_info,
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
        """Probar texto sin URL de imagen."""
        text = "Mensaje simple sin imagen"
        embed, clean_text = create_panel_embed(text)

        assert embed is None
        assert clean_text == text

    def test_with_png_image(self) -> None:
        """Probar texto con URL de imagen PNG."""
        text = "Bienvenido al servidor\nhttps://example.com/image.png"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "image.png" not in clean_text
        assert "Bienvenido" in clean_text

    def test_with_jpg_image(self) -> None:
        """Probar texto con URL de imagen JPG."""
        text = "Texto con imagen https://example.com/photo.jpg aqui"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None
        assert "photo.jpg" not in clean_text

    def test_with_jpeg_image(self) -> None:
        """Probar texto con URL de imagen JPEG."""
        text = "https://example.com/photo.jpeg"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None

    def test_with_gif_image(self) -> None:
        """Probar texto con URL de imagen GIF."""
        text = "Animacion: https://example.com/animation.gif"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None

    def test_with_webp_image(self) -> None:
        """Probar texto con URL de imagen WEBP."""
        text = "Imagen moderna: https://example.com/image.webp"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None

    def test_with_query_params(self) -> None:
        """Probar URL de imagen con parametros de query."""
        text = "Imagen: https://example.com/image.png?width=100&height=200"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None
        assert "width=100" not in clean_text

    def test_removes_extra_newlines(self) -> None:
        """Probar que elimina lineas vacias extra."""
        text = "Primera linea\n\n\nhttps://example.com/image.png\n\n\nUltima linea"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None
        # No debe haber mas de 2 saltos de linea consecutivos
        assert "\n\n\n" not in clean_text

    def test_embed_has_blurple_color(self) -> None:
        """Probar que el embed tiene color blurple."""
        text = "Texto https://example.com/image.png"
        embed, _ = create_panel_embed(text)

        assert embed is not None
        assert embed.color == discord.Color.blurple()

    def test_embed_description_contains_text(self) -> None:
        """Probar que el embed contiene el texto en la descripcion."""
        text = "Contenido del mensaje https://example.com/image.png"
        embed, _ = create_panel_embed(text)

        assert embed is not None
        assert "Contenido del mensaje" in (embed.description or "")

    def test_case_insensitive_extension(self) -> None:
        """Probar que la extension es case insensitive."""
        text = "Imagen: https://example.com/image.PNG"
        embed, clean_text = create_panel_embed(text)

        assert embed is not None


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


class TestFormatPlayerInfo:
    """Tests para format_player_info."""

    def test_format_all_fields(self) -> None:
        """Probar formateo con todos los campos."""
        template = "Name: {name}, Level: {level}, Faction: {faction}"
        api_response = VerificationAPIResponse(
            name="TestPlayer",
            level=25,
            regiment="TestRegiment",
            faction="colonial",
            shard="ABLE",
            ingame_time="268, 07:41",
            war=100,
            current_ingame_time="278, 08:34",
        )

        result = format_player_info(template, api_response)

        assert "TestPlayer" in result
        assert "25" in result
        assert "colonial" in result

    def test_format_with_empty_regiment(self) -> None:
        """Probar formateo cuando regiment está vacío."""
        template = "Regiment: {regiment}"
        api_response = VerificationAPIResponse(
            name="TestPlayer",
            level=25,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="268, 07:41",
            war=100,
            current_ingame_time="278, 08:34",
        )

        result = format_player_info(template, api_response)

        assert "N/A" in result

    def test_format_with_none_template(self) -> None:
        """Probar con template None."""
        api_response = VerificationAPIResponse(
            name="TestPlayer",
            level=25,
            regiment="TestRegiment",
            faction="colonial",
            shard="ABLE",
            ingame_time="268, 07:41",
            war=100,
            current_ingame_time="278, 08:34",
        )

        result = format_player_info(None, api_response)

        assert result == ""

    def test_format_with_all_placeholders(self) -> None:
        """Probar formateo con todos los placeholders disponibles."""
        template = (
            "{name} - {regiment} - {level} - {faction} - {shard} - {time} - {war} - {war_time}"
        )
        api_response = VerificationAPIResponse(
            name="Player",
            level=50,
            regiment="Regiment",
            faction="wardens",
            shard="CHARLIE",
            ingame_time="100, 12:00",
            war=50,
            current_ingame_time="110, 14:00",
        )

        result = format_player_info(template, api_response)

        assert "Player" in result
        assert "Regiment" in result
        assert "50" in result
        assert "wardens" in result
        assert "CHARLIE" in result
        assert "100, 12:00" in result
        assert "110, 14:00" in result
