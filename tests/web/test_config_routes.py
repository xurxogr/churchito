"""Tests para las rutas de configuración."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import ConfigSchemaService
from discord_bot.web.routers.config import (
    cog_settings,
    guild_config,
    reset_cog_config,
    toggle_cog,
    update_option,
)


@pytest.fixture
def mock_schema_service() -> ConfigSchemaService:
    """Crear schema service con datos de prueba.

    Returns:
        ConfigSchemaService: Servicio de esquemas
    """
    service = ConfigSchemaService()
    service.register_schema(
        CogConfigSchema(
            cog_name="test_cog",
            display_name="Test Cog",
            description="A test cog",
            icon="🧪",
            options=[
                ConfigOption(
                    key="string_option",
                    name="String Option",
                    option_type=ConfigOptionType.STRING,
                    default="default",
                ),
                ConfigOption(
                    key="channel_option",
                    name="Channel Option",
                    option_type=ConfigOptionType.CHANNEL,
                ),
                ConfigOption(
                    key="role_option",
                    name="Role Option",
                    option_type=ConfigOptionType.ROLE,
                ),
                ConfigOption(
                    key="channel_list",
                    name="Channel List",
                    option_type=ConfigOptionType.CHANNEL_LIST,
                    default=[],
                ),
                ConfigOption(
                    key="role_list",
                    name="Role List",
                    option_type=ConfigOptionType.ROLE_LIST,
                    default=[],
                ),
            ],
        )
    )
    return service


@pytest.fixture
def mock_config_request(simple_app: FastAPI, test_user: dict[str, Any]) -> MagicMock:
    """Crear request mock para config.

    Args:
        simple_app (FastAPI): Aplicación
        test_user (dict[str, Any]): Usuario

    Returns:
        MagicMock: Request mock
    """
    request = MagicMock(spec=Request)
    request.app = simple_app

    # Mock templates
    request.app.state.templates = MagicMock(spec=Jinja2Templates)
    mock_response = MagicMock()
    request.app.state.templates.TemplateResponse.return_value = mock_response

    # Mock bot
    request.app.state.bot = MagicMock()
    request.app.state.bot.get_guild.return_value = None

    return request


class TestGuildConfig:
    """Tests para la ruta de configuración de guild."""

    async def test_guild_config_shows_cogs(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar que guild_config muestra los cogs."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_enabled_cogs = AsyncMock(return_value={})
            mock_config_service_class.return_value = mock_config_service

            await guild_config(mock_config_request, 111222333, test_user, test_session)

            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            assert "cogs" in context
            assert len(context["cogs"]) == 1
            assert context["cogs"][0]["name"] == "test_cog"


class TestCogSettings:
    """Tests para la ruta de configuración de cog."""

    async def test_cog_settings_shows_options(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar que cog_settings muestra las opciones."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            assert "options" in context
            assert context["cog_name"] == "test_cog"
            assert context["enabled"] is True

    async def test_cog_settings_with_discord_guild(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar cog_settings cuando el bot está en el guild."""
        # Setup mock Discord guild
        mock_channel = MagicMock()
        mock_channel.id = 123
        mock_channel.name = "general"
        mock_channel.category = MagicMock()
        mock_channel.category.name = "Text Channels"

        mock_role = MagicMock()
        mock_role.id = 456
        mock_role.name = "Admin"
        mock_role.color = MagicMock()
        mock_role.color.__str__ = MagicMock(return_value="#ff0000")

        mock_everyone_role = MagicMock()
        mock_everyone_role.name = "@everyone"

        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        mock_guild.roles = [mock_everyone_role, mock_role]
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_role.return_value = mock_role

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(
                return_value={"channel_option": 123, "role_option": 456}
            )
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            assert "channels" in context
            assert "roles" in context
            assert len(context["channels"]) == 1
            assert len(context["roles"]) == 1  # @everyone excluded

    async def test_cog_settings_not_found(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar cog_settings cuando el cog no existe."""
        empty_service = ConfigSchemaService()

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=empty_service,
            ),
            pytest.raises(HTTPException),
        ):
            await cog_settings(
                mock_config_request, 111222333, "nonexistent", test_user, test_session
            )


class TestToggleCog:
    """Tests para toggle_cog."""

    async def test_toggle_cog_enables(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar que toggle_cog alterna el estado."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service.set_cog_enabled = AsyncMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service_class.return_value = mock_config_service

            await toggle_cog(mock_config_request, 111222333, "test_cog", test_user, test_session)

            # Verificar que se llamó a set_cog_enabled con False (toggle de True)
            mock_config_service.set_cog_enabled.assert_called_once_with(
                111222333, "test_cog", False
            )


class TestUpdateOption:
    """Tests para update_option."""

    async def test_update_option_success(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar actualización de opción exitosa."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.set_value = AsyncMock(return_value=(True, None))
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_option(
                mock_config_request,
                111222333,
                "test_cog",
                "string_option",
                "new_value",
                test_user,
                test_session,
            )

            mock_config_service.set_value.assert_called_once()

    async def test_update_option_not_found(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar actualización de opción inexistente."""
        empty_service = ConfigSchemaService()

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=empty_service,
            ),
            pytest.raises(HTTPException),
        ):
            await update_option(
                mock_config_request,
                111222333,
                "test_cog",
                "nonexistent",
                "value",
                test_user,
                test_session,
            )


class TestResetCogConfig:
    """Tests para reset_cog_config."""

    async def test_reset_config_success(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar reset de configuración exitoso."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.reset_config = AsyncMock(return_value=3)
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await reset_cog_config(
                mock_config_request, 111222333, "test_cog", test_user, test_session
            )

            mock_config_service.reset_config.assert_called_once_with(111222333, "test_cog")
