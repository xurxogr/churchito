"""Tests para discord_bot/purga/config.py."""

import discord

from discord_bot.purga.config import (
    BUTTON_STYLES,
    COG_NAME,
    DEFAULT_MOD_MESSAGE,
    DEFAULT_USER_MESSAGE,
    PURGA_CONFIG_SCHEMA,
)


class TestButtonStyles:
    """Tests para BUTTON_STYLES."""

    def test_blurple_style(self) -> None:
        """Probar estilo blurple."""
        assert BUTTON_STYLES["blurple"] == discord.ButtonStyle.primary

    def test_grey_style(self) -> None:
        """Probar estilo grey."""
        assert BUTTON_STYLES["grey"] == discord.ButtonStyle.secondary

    def test_green_style(self) -> None:
        """Probar estilo green."""
        assert BUTTON_STYLES["green"] == discord.ButtonStyle.success

    def test_red_style(self) -> None:
        """Probar estilo red."""
        assert BUTTON_STYLES["red"] == discord.ButtonStyle.danger


class TestCogName:
    """Tests para COG_NAME."""

    def test_cog_name_value(self) -> None:
        """Probar que el nombre del cog es correcto."""
        assert COG_NAME == "purga"


class TestDefaultMessages:
    """Tests para plantillas de mensajes por defecto."""

    def test_mod_message_has_placeholders(self) -> None:
        """Probar que el mensaje de moderación tiene los placeholders necesarios."""
        assert "{purge_type}" in DEFAULT_MOD_MESSAGE
        assert "{status}" in DEFAULT_MOD_MESSAGE
        assert "{required_reactions}" in DEFAULT_MOD_MESSAGE
        assert "{authorized_by}" in DEFAULT_MOD_MESSAGE
        assert "{cancellations}" in DEFAULT_MOD_MESSAGE
        assert "{dia}" in DEFAULT_MOD_MESSAGE

    def test_user_message_has_placeholders(self) -> None:
        """Probar que el mensaje de usuarios tiene los placeholders necesarios."""
        assert "{roles}" in DEFAULT_USER_MESSAGE
        assert "{dia}" in DEFAULT_USER_MESSAGE
        assert "{reaction_rol}" in DEFAULT_USER_MESSAGE


class TestPurgaConfigSchema:
    """Tests para PURGA_CONFIG_SCHEMA."""

    def test_schema_cog_name(self) -> None:
        """Probar nombre del cog en el schema."""
        assert PURGA_CONFIG_SCHEMA.cog_name == "purga"

    def test_schema_display_name(self) -> None:
        """Probar nombre de display."""
        assert PURGA_CONFIG_SCHEMA.display_name == "Purga"

    def test_schema_is_toggleable(self) -> None:
        """Probar que el cog es toggleable."""
        assert PURGA_CONFIG_SCHEMA.toggleable is True

    def test_schema_has_options(self) -> None:
        """Probar que el schema tiene opciones."""
        assert len(PURGA_CONFIG_SCHEMA.options) > 0

    def test_schema_has_mod_channel_option(self) -> None:
        """Probar que existe la opción de canal de moderación."""
        keys = [opt.key for opt in PURGA_CONFIG_SCHEMA.options]
        assert "mod_channel" in keys

    def test_schema_has_user_channel_option(self) -> None:
        """Probar que existe la opción de canal de usuarios."""
        keys = [opt.key for opt in PURGA_CONFIG_SCHEMA.options]
        assert "user_channel" in keys

    def test_schema_has_war_admin_roles_option(self) -> None:
        """Probar que existe la opción de roles administradores."""
        keys = [opt.key for opt in PURGA_CONFIG_SCHEMA.options]
        assert "war_admin_roles" in keys

    def test_schema_has_war_affected_roles_option(self) -> None:
        """Probar que existe la opción de roles afectados."""
        keys = [opt.key for opt in PURGA_CONFIG_SCHEMA.options]
        assert "war_affected_roles" in keys

    def test_schema_has_icon(self) -> None:
        """Probar que el schema tiene un icono."""
        assert PURGA_CONFIG_SCHEMA.icon is not None
