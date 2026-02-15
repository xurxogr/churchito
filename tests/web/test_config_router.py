"""Tests para el router de configuración."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.web.routers.config import (
    _convert_form_value,
    _get_guild_info,
    _validate_channel_permissions,
    get_templates,
    guild_access_dep,
    router,
)


@pytest.fixture
def config_app(simple_app: FastAPI) -> FastAPI:
    """Crear aplicación con router de config.

    Args:
        simple_app (FastAPI): Aplicación base

    Returns:
        FastAPI: Aplicación con config router
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def config_client(config_app: FastAPI) -> TestClient:
    """Crear cliente para config.

    Args:
        config_app (FastAPI): Aplicación

    Returns:
        TestClient: Cliente de prueba
    """
    return TestClient(config_app)


class TestGetTemplates:
    """Tests para get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Probar que retorna templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestGetGuildInfo:
    """Tests para _get_guild_info."""

    def test_returns_guild_when_found(self, test_user: dict[str, Any]) -> None:
        """Probar que retorna info del guild cuando existe."""
        result = _get_guild_info(test_user, 111222333)
        assert result["name"] == "Test Guild"

    def test_returns_default_when_not_found(self, test_user: dict[str, Any]) -> None:
        """Probar que retorna info por defecto cuando no existe."""
        result = _get_guild_info(test_user, 999999)
        assert result["id"] == "999999"
        assert "Servidor" in result["name"]


class TestConvertFormValue:
    """Tests para _convert_form_value."""

    def test_convert_empty_returns_none(self) -> None:
        """Probar que valor vacío retorna None."""
        result = _convert_form_value("", ConfigOptionType.STRING)
        assert result is None

    def test_convert_integer(self) -> None:
        """Probar conversión a entero."""
        result = _convert_form_value("42", ConfigOptionType.INTEGER)
        assert result == 42

    def test_convert_boolean_true(self) -> None:
        """Probar conversión a booleano True."""
        for value in ["true", "1", "on", "yes", "sí"]:
            result = _convert_form_value(value, ConfigOptionType.BOOLEAN)
            assert result is True

    def test_convert_boolean_false(self) -> None:
        """Probar conversión a booleano False."""
        result = _convert_form_value("false", ConfigOptionType.BOOLEAN)
        assert result is False

    def test_convert_channel(self) -> None:
        """Probar conversión de canal."""
        result = _convert_form_value("123456789", ConfigOptionType.CHANNEL)
        assert result == 123456789

    def test_convert_role(self) -> None:
        """Probar conversión de rol."""
        result = _convert_form_value("987654321", ConfigOptionType.ROLE)
        assert result == 987654321

    def test_convert_channel_list(self) -> None:
        """Probar conversión de lista de canales."""
        result = _convert_form_value("123,456,789", ConfigOptionType.CHANNEL_LIST)
        assert result == [123, 456, 789]

    def test_convert_channel_list_empty(self) -> None:
        """Probar conversión de lista de canales vacía."""
        result = _convert_form_value("", ConfigOptionType.CHANNEL_LIST)
        assert result is None

    def test_convert_role_list(self) -> None:
        """Probar conversión de lista de roles."""
        result = _convert_form_value("111,222,333", ConfigOptionType.ROLE_LIST)
        assert result == [111, 222, 333]

    def test_convert_string(self) -> None:
        """Probar conversión de string."""
        result = _convert_form_value("hello world", ConfigOptionType.STRING)
        assert result == "hello world"

    def test_convert_text_choice(self) -> None:
        """Probar conversión de text choice."""
        result = _convert_form_value("option_a", ConfigOptionType.TEXT_CHOICE)
        assert result == "option_a"


class TestValidateChannelPermissions:
    """Tests para _validate_channel_permissions."""

    def test_returns_none_when_no_bot(self, simple_app: FastAPI) -> None:
        """Probar que retorna None cuando no hay bot."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = None

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_none_when_guild_not_found(self, simple_app: FastAPI) -> None:
        """Probar que retorna None cuando no se encuentra el guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = None

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_error_when_channel_not_found(self, simple_app: FastAPI) -> None:
        """Probar que retorna error cuando no se encuentra el canal."""
        request = MagicMock()
        request.app = simple_app
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = None
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild

        result = _validate_channel_permissions(request, 123, 456)
        assert result is not None
        assert "456" in result
        assert "no encontrado" in result

    def test_returns_none_when_bot_member_not_found(self, simple_app: FastAPI) -> None:
        """Probar que retorna None cuando no se encuentra el miembro bot."""
        request = MagicMock()
        request.app = simple_app
        mock_channel = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = None
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_error_when_no_send_permission(self, simple_app: FastAPI) -> None:
        """Probar que retorna error cuando no tiene permisos de enviar."""
        request = MagicMock()
        request.app = simple_app
        mock_permissions = MagicMock()
        mock_permissions.send_messages = False
        mock_channel = MagicMock()
        mock_channel.name = "test-channel"
        mock_channel.permissions_for.return_value = mock_permissions
        mock_bot_member = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = mock_bot_member
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is not None
        assert "test-channel" in result
        assert "permiso" in result.lower()

    def test_returns_none_when_has_permission(self, simple_app: FastAPI) -> None:
        """Probar que retorna None cuando tiene permisos."""
        request = MagicMock()
        request.app = simple_app
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_channel = MagicMock()
        mock_channel.permissions_for.return_value = mock_permissions
        mock_bot_member = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = mock_bot_member
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None


class TestGuildAccessDep:
    """Tests para guild_access_dep."""

    async def test_returns_user_when_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que retorna usuario cuando tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        result = await guild_access_dep(request, 111222333, test_user)
        assert result == test_user
