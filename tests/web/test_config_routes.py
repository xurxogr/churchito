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
    request.scope = {"root_path": ""}

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
                test_user,
                test_session,
                value="new_value",
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
                test_user,
                test_session,
                value="value",
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


class TestCogSettingsDisplayValues:
    """Tests para display_value de CHANNEL_LIST y ROLE_LIST."""

    async def test_cog_settings_channel_list_display(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar display value de CHANNEL_LIST."""
        # Setup mock Discord guild con canales
        mock_channel1 = MagicMock()
        mock_channel1.id = 111
        mock_channel1.name = "general"
        mock_channel1.category = MagicMock()
        mock_channel1.category.name = "Text"

        mock_channel2 = MagicMock()
        mock_channel2.id = 222
        mock_channel2.name = "help"
        mock_channel2.category = MagicMock()
        mock_channel2.category.name = "Text"

        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel1, mock_channel2]
        mock_guild.roles = []

        def get_channel_side_effect(channel_id: int) -> MagicMock | None:
            if channel_id == 111:
                return mock_channel1
            if channel_id == 222:
                return mock_channel2
            return None

        mock_guild.get_channel.side_effect = get_channel_side_effect
        mock_guild.get_role.return_value = None

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
                return_value={"channel_list": [111, 222]}
            )
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            # Verificar que las opciones incluyen channel_list con display_value
            channel_list_opt = next(
                (o for o in context["options"] if o["key"] == "channel_list"), None
            )
            assert channel_list_opt is not None
            assert "#general" in channel_list_opt["display_value"]
            assert "#help" in channel_list_opt["display_value"]

    async def test_cog_settings_role_list_display(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar display value de ROLE_LIST."""
        mock_role1 = MagicMock()
        mock_role1.id = 333
        mock_role1.name = "Admin"
        mock_role1.color = MagicMock()
        mock_role1.color.__str__ = MagicMock(return_value="#ff0000")

        mock_role2 = MagicMock()
        mock_role2.id = 444
        mock_role2.name = "Mod"
        mock_role2.color = MagicMock()
        mock_role2.color.__str__ = MagicMock(return_value="#00ff00")

        mock_everyone_role = MagicMock()
        mock_everyone_role.name = "@everyone"

        mock_guild = MagicMock()
        mock_guild.text_channels = []
        mock_guild.roles = [mock_everyone_role, mock_role1, mock_role2]
        mock_guild.get_channel.return_value = None

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 333:
                return mock_role1
            if role_id == 444:
                return mock_role2
            return None

        mock_guild.get_role.side_effect = get_role_side_effect

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={"role_list": [333, 444]})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            # Verificar que las opciones incluyen role_list con display_value
            role_list_opt = next((o for o in context["options"] if o["key"] == "role_list"), None)
            assert role_list_opt is not None
            assert "@Admin" in role_list_opt["display_value"]
            assert "@Mod" in role_list_opt["display_value"]

    async def test_cog_settings_list_with_unknown_ids(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar display value cuando los IDs no se encuentran."""
        mock_guild = MagicMock()
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.get_channel.return_value = None
        mock_guild.get_role.return_value = None

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
                return_value={"channel_list": [999], "role_list": [888]}
            )
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            # Debe mostrar "ID: xxx" cuando no se encuentra
            channel_list_opt = next(
                (o for o in context["options"] if o["key"] == "channel_list"), None
            )
            assert channel_list_opt is not None
            assert "ID: 999" in channel_list_opt["display_value"]

            role_list_opt = next((o for o in context["options"] if o["key"] == "role_list"), None)
            assert role_list_opt is not None
            assert "ID: 888" in role_list_opt["display_value"]


class TestUpdateOptionError:
    """Tests para errores en update_option."""

    async def test_update_option_set_value_fails(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar actualización de opción cuando set_value falla."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch("discord_bot.web.routers.config.logger") as mock_logger,
        ):
            mock_config_service = MagicMock()
            # Simular fallo en set_value
            mock_config_service.set_value = AsyncMock(return_value=(False, "Error de validación"))
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_option(
                mock_config_request,
                111222333,
                "test_cog",
                "string_option",
                test_user,
                test_session,
                value="invalid_value",
            )

            # Debe loguear el warning
            mock_logger.warning.assert_called_once()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "Error al guardar configuración" in warning_message


class TestNotifyCogConfigChanged:
    """Tests para _notify_cog_config_changed."""

    async def test_bot_is_none(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando bot es None."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_config_request.app.state.bot = None

        # No debería fallar
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            key="test_key",
        )

    async def test_guild_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando guild no existe."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_config_request.app.state.bot.get_guild.return_value = None

        # No debería fallar
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            key="test_key",
        )

    async def test_calls_on_config_changed(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que llama on_config_changed cuando el cog existe."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_config_changed = AsyncMock()

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            key="test_key",
        )

        mock_cog.on_config_changed.assert_called_once_with(guild=mock_guild, key="test_key")

    async def test_handles_exception_in_on_config_changed(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que maneja excepciones en on_config_changed."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_config_changed = AsyncMock(side_effect=Exception("Error de prueba"))

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        with patch("discord_bot.web.routers.config.logger") as mock_logger:
            # No debería fallar
            await _notify_cog_config_changed(
                request=mock_config_request,
                guild_id=123,
                cog_name="test_cog",
                key="test_key",
            )

            mock_logger.error.assert_called_once()

    async def test_cog_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando el cog no existe."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_guild = MagicMock()
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        # No debería fallar
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            key="test_key",
        )


class TestNotifyCogToggled:
    """Tests para _notify_cog_toggled."""

    async def test_bot_is_none(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando bot es None."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_config_request.app.state.bot = None

        # No debería fallar
        await _notify_cog_toggled(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            enabled=True,
        )

    async def test_guild_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando guild no existe."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_config_request.app.state.bot.get_guild.return_value = None

        # No debería fallar
        await _notify_cog_toggled(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            enabled=True,
        )

    async def test_calls_on_cog_toggled(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que llama on_cog_toggled cuando el cog existe."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_cog_toggled = AsyncMock()

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        await _notify_cog_toggled(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            enabled=True,
        )

        mock_cog.on_cog_toggled.assert_called_once_with(guild=mock_guild, enabled=True)

    async def test_handles_exception_in_on_cog_toggled(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que maneja excepciones en on_cog_toggled."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_cog_toggled = AsyncMock(side_effect=Exception("Error de prueba"))

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        with patch("discord_bot.web.routers.config.logger") as mock_logger:
            # No debería fallar
            await _notify_cog_toggled(
                request=mock_config_request,
                guild_id=123,
                cog_name="test_cog",
                enabled=False,
            )

            mock_logger.error.assert_called_once()

    async def test_cog_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Probar que no falla cuando el cog no existe."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_guild = MagicMock()
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        # No debería fallar
        await _notify_cog_toggled(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            enabled=True,
        )


class TestChannelPermissionValidation:
    """Tests para validación de permisos de canal."""

    async def test_channel_permission_error(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Probar que muestra error cuando el bot no tiene permisos en el canal."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch("discord_bot.web.routers.config._validate_channel_permissions") as mock_validate,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            # Simular error de permisos
            mock_validate.return_value = "El bot no puede enviar mensajes en ese canal"

            await update_option(
                mock_config_request,
                111222333,
                "test_cog",
                "channel_option",
                test_user,
                test_session,
                value="123456789",  # ID de canal
            )

            # Debe mostrar error
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert context.get("error") == "El bot no puede enviar mensajes en ese canal"
