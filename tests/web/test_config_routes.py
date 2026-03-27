"""Tests for configuration routes."""

import json
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
    _convert_form_value,
    cog_settings,
    guild_config,
    reload_cog,
    toggle_cog,
    update_option,
)


@pytest.fixture
def mock_schema_service() -> ConfigSchemaService:
    """Create schema service with test data.

    Returns:
        ConfigSchemaService: Schema service
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
    """Create mock request for config.

    Args:
        simple_app (FastAPI): Application
        test_user (dict[str, Any]): User

    Returns:
        MagicMock: Mock request
    """
    request = MagicMock(spec=Request)
    request.app = simple_app
    request.scope = {"root_path": ""}
    request.headers = {"content-type": "application/json"}

    # Mock templates
    request.app.state.templates = MagicMock(spec=Jinja2Templates)
    mock_response = MagicMock()
    request.app.state.templates.TemplateResponse.return_value = mock_response

    # Mock bot with a guild
    mock_guild = MagicMock()
    mock_guild.id = 111222333
    request.app.state.bot = MagicMock()
    request.app.state.bot.get_guild.return_value = mock_guild

    return request


class TestGuildConfig:
    """Tests for the guild configuration route."""

    async def test_guild_config_shows_cogs(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that guild_config shows the cogs."""
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

    async def test_guild_config_bot_not_in_guild(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that guild_config raises 404 when bot is not in guild."""
        # Bot doesn't find the guild
        mock_config_request.app.state.bot.get_guild.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await guild_config(mock_config_request, 999888777, test_user, test_session)

        assert exc_info.value.status_code == 404
        assert "don't have permission" in exc_info.value.detail

    async def test_guild_config_no_bot(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that guild_config raises 404 when there is no bot."""
        mock_config_request.app.state.bot = None

        with pytest.raises(HTTPException) as exc_info:
            await guild_config(mock_config_request, 111222333, test_user, test_session)

        assert exc_info.value.status_code == 404


class TestCogSettings:
    """Tests for the cog configuration route."""

    async def test_cog_settings_shows_options(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that cog_settings shows the options."""
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
        """Test cog_settings when bot is in guild."""
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

        # Bot's top role (higher than other roles)
        mock_bot_top_role = MagicMock()
        mock_bot_top_role.position = 100

        # Configure role comparison (role < bot_top_role)
        mock_role.__lt__ = MagicMock(return_value=True)
        mock_everyone_role.__lt__ = MagicMock(return_value=True)

        mock_bot_member = MagicMock()
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        mock_guild.roles = [mock_everyone_role, mock_role]
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_role.return_value = mock_role
        mock_guild.me = mock_bot_member

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
        """Test cog_settings when cog doesn't exist."""
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

    async def test_cog_settings_locked_options_exception_handled(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that get_locked_options exception doesn't crash."""
        # Setup mock cog that raises exception
        mock_cog = MagicMock()
        mock_cog.get_locked_options = MagicMock(side_effect=RuntimeError("Test error"))
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

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

            # Should not raise exception
            await cog_settings(mock_config_request, 111222333, "test_cog", test_user, test_session)

            # Should still render the template
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()

    async def test_cog_settings_locked_options_excluded(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that locked options don't appear in the list."""
        # Setup mock cog that locks string_option
        mock_cog = MagicMock()
        mock_cog.get_locked_options.return_value = {"string_option": "Locked reason"}
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

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

            # Verify template was called
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()

            # Get the context passed to the template
            call_args = mock_config_request.app.state.templates.TemplateResponse.call_args
            context = call_args[1]["context"]

            # Verify string_option is NOT in the options list
            option_keys = [opt["key"] for opt in context["options"]]
            assert "string_option" not in option_keys
            # But other options should still be there
            assert "channel_option" in option_keys


class TestToggleCog:
    """Tests for toggle_cog."""

    async def test_toggle_cog_enables(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that toggle_cog toggles the state."""
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

            # Verify set_cog_enabled was called with False (toggle from True)
            mock_config_service.set_cog_enabled.assert_called_once_with(
                111222333, "test_cog", False
            )


class TestUpdateOption:
    """Tests for update_option."""

    async def test_update_option_success(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test successful option update."""
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
        """Test update of nonexistent option."""
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


class TestReloadCog:
    """Tests for reload_cog."""

    async def test_reload_cog_success(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test successful cog reload."""
        mock_bot = MagicMock()
        mock_bot.reload_extension = AsyncMock()
        mock_config_request.app.state.bot = mock_bot

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

            await reload_cog(mock_config_request, 111222333, "test_cog", test_user, test_session)

            mock_bot.reload_extension.assert_called_once_with("discord_bot.test_cog.cog")

    async def test_reload_bot_cog_not_allowed(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that 'bot' cog cannot be reloaded."""
        # Create schema service with "bot" registered
        service = ConfigSchemaService()
        service.register_schema(
            CogConfigSchema(
                cog_name="bot",
                display_name="Bot",
                description="Bot core",
                icon="🤖",
                options=[],
            )
        )

        with patch(
            "discord_bot.web.routers.config.get_config_schema_service",
            return_value=service,
        ):
            await reload_cog(mock_config_request, 111222333, "bot", test_user, test_session)

            # Should return template with error
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert "error" in context
            assert "cannot be reloaded" in context["error"]

    async def test_reload_cog_bot_not_available(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test reload when bot is not available."""
        mock_config_request.app.state.bot = None

        with patch(
            "discord_bot.web.routers.config.get_config_schema_service",
            return_value=mock_schema_service,
        ):
            await reload_cog(mock_config_request, 111222333, "test_cog", test_user, test_session)

            # Should return template with error
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert "error" in context
            assert "Bot not available" in context["error"]

    async def test_reload_cog_exception(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test reload when extension fails to reload."""
        mock_bot = MagicMock()
        mock_bot.reload_extension = AsyncMock(side_effect=Exception("Extension not found"))
        mock_config_request.app.state.bot = mock_bot

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

            await reload_cog(mock_config_request, 111222333, "test_cog", test_user, test_session)

            # Should return template with error
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert "error" in context
            assert "Error reloading" in context["error"]


class TestCogSettingsDisplayValues:
    """Tests for display_value of CHANNEL_LIST and ROLE_LIST."""

    async def test_cog_settings_channel_list_display(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test display value of CHANNEL_LIST."""
        # Setup mock Discord guild with channels
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

            # Verify options include channel_list with display_value
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
        """Test display value of ROLE_LIST."""
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

        # Configure role comparison (roles are below bot's top role)
        mock_role1.__lt__ = MagicMock(return_value=True)
        mock_role2.__lt__ = MagicMock(return_value=True)
        mock_everyone_role.__lt__ = MagicMock(return_value=True)

        mock_bot_top_role = MagicMock()
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild = MagicMock()
        mock_guild.text_channels = []
        mock_guild.roles = [mock_everyone_role, mock_role1, mock_role2]
        mock_guild.get_channel.return_value = None
        mock_guild.me = mock_bot_member

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

            # Verify options include role_list with display_value
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
        """Test display value when IDs are not found."""
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

            # Should show "ID: xxx" when not found
            channel_list_opt = next(
                (o for o in context["options"] if o["key"] == "channel_list"), None
            )
            assert channel_list_opt is not None
            assert "ID: 999" in channel_list_opt["display_value"]

            role_list_opt = next((o for o in context["options"] if o["key"] == "role_list"), None)
            assert role_list_opt is not None
            assert "ID: 888" in role_list_opt["display_value"]


class TestUpdateOptionError:
    """Tests for errors in update_option."""

    async def test_update_option_set_value_fails(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test option update when set_value fails."""
        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch("discord_bot.web.routers.config.logger") as mock_logger,
        ):
            mock_config_service = MagicMock()
            # Simulate failure in set_value
            mock_config_service.set_value = AsyncMock(return_value=(False, "Validation error"))
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

            # Should log the warning
            mock_logger.warning.assert_called_once()
            warning_message = mock_logger.warning.call_args[0][0]
            assert "Error saving configuration" in warning_message


class TestNotifyCogConfigChanged:
    """Tests for _notify_cog_config_changed."""

    async def test_bot_is_none(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it doesn't fail when bot is None."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_config_request.app.state.bot = None

        # Should not fail
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            keys=["test_key"],
        )

    async def test_guild_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it doesn't fail when guild doesn't exist."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_config_request.app.state.bot.get_guild.return_value = None

        # Should not fail
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            keys=["test_key"],
        )

    async def test_calls_on_config_changed(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it calls on_config_changed when cog exists."""
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
            keys=["test_key"],
        )

        mock_cog.on_config_changed.assert_called_once_with(guild=mock_guild, keys=["test_key"])

    async def test_handles_exception_in_on_config_changed(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it handles exceptions in on_config_changed."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_config_changed = AsyncMock(side_effect=Exception("Test error"))

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        with patch("discord_bot.web.routers.config.logger") as mock_logger:
            # Should not fail
            await _notify_cog_config_changed(
                request=mock_config_request,
                guild_id=123,
                cog_name="test_cog",
                keys=["test_key"],
            )

            mock_logger.error.assert_called_once()

    async def test_cog_not_found(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it doesn't fail when cog doesn't exist."""
        from discord_bot.web.routers.config import _notify_cog_config_changed

        mock_guild = MagicMock()
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        # Should not fail
        await _notify_cog_config_changed(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            keys=["test_key"],
        )


class TestNotifyCogToggled:
    """Tests for _notify_cog_toggled."""

    async def test_bot_is_none(
        self,
        mock_config_request: MagicMock,
    ) -> None:
        """Test that it doesn't fail when bot is None."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_config_request.app.state.bot = None

        # Should not fail
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
        """Test that it doesn't fail when guild doesn't exist."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_config_request.app.state.bot.get_guild.return_value = None

        # Should not fail
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
        """Test that it calls on_cog_toggled when cog exists."""
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
        """Test that it handles exceptions in on_cog_toggled."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_guild = MagicMock()
        mock_cog = MagicMock()
        mock_cog.on_cog_toggled = AsyncMock(side_effect=Exception("Test error"))

        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = mock_cog

        with patch("discord_bot.web.routers.config.logger") as mock_logger:
            # Should not fail
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
        """Test that it doesn't fail when cog doesn't exist."""
        from discord_bot.web.routers.config import _notify_cog_toggled

        mock_guild = MagicMock()
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        # Should not fail
        await _notify_cog_toggled(
            request=mock_config_request,
            guild_id=123,
            cog_name="test_cog",
            enabled=True,
        )


class TestChannelPermissionValidation:
    """Tests for channel permission validation."""

    async def test_channel_permission_error(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that it shows error when bot doesn't have permissions in channel."""
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

            # Simulate permission error
            mock_validate.return_value = "Bot cannot send messages in that channel"

            await update_option(
                mock_config_request,
                111222333,
                "test_cog",
                "channel_option",
                test_user,
                test_session,
                value="123456789",  # Channel ID
            )

            # Should show error
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert context.get("error") == "Bot cannot send messages in that channel"


class TestToggleCogInvalidCog:
    """Tests for toggle_cog with invalid cog."""

    async def test_toggle_cog_invalid_cog_raises_404(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that toggle_cog raises 404 for nonexistent cog."""
        empty_service = ConfigSchemaService()

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=empty_service,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await toggle_cog(
                mock_config_request, 111222333, "nonexistent_cog", test_user, test_session
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Cog not found"


class TestReloadCogInvalidCog:
    """Tests for reload_cog with invalid cog."""

    async def test_reload_cog_invalid_cog_raises_404(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that reload_cog raises 404 for nonexistent cog."""
        empty_service = ConfigSchemaService()

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=empty_service,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await reload_cog(
                mock_config_request, 111222333, "nonexistent_cog", test_user, test_session
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Cog not found"


class TestConvertFormValueTable:
    """Tests for _convert_form_value with TABLE type."""

    def test_table_valid_json_list(self) -> None:
        """Test conversion of valid JSON as list."""
        value = '[{"key": "value"}]'
        result = _convert_form_value(value, ConfigOptionType.TABLE)
        assert result == [{"key": "value"}]

    def test_table_json_too_large(self) -> None:
        """Test that JSON too large returns None."""
        # Create JSON larger than 100KB
        large_value = "[" + ",".join(['{"x": "y"}'] * 20000) + "]"
        assert len(large_value) > 100_000

        result = _convert_form_value(large_value, ConfigOptionType.TABLE)
        assert result is None

    def test_table_invalid_json(self) -> None:
        """Test that invalid JSON returns None."""
        value = "not valid json {"
        result = _convert_form_value(value, ConfigOptionType.TABLE)
        assert result is None

    def test_table_not_a_list(self) -> None:
        """Test that JSON that is not a list returns None."""
        value = '{"key": "value"}'
        result = _convert_form_value(value, ConfigOptionType.TABLE)
        assert result is None

    def test_table_with_columns_filters_keys(self) -> None:
        """Test that invalid keys are filtered according to columns."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "valid_key", "name": "Valid"},
                {"key": "another_key", "name": "Another"},
            ],
        )
        value = '[{"valid_key": "v1", "invalid_key": "v2", "another_key": "v3"}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"valid_key": "v1", "another_key": "v3"}]

    def test_table_with_role_column_converts_to_int(self) -> None:
        """Test that role type columns are converted to int."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role"},
                {"key": "name", "name": "Name"},
            ],
        )
        value = '[{"role_id": "123456", "name": "Test"}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"role_id": 123456, "name": "Test"}]

    def test_table_with_channel_column_converts_to_int(self) -> None:
        """Test that channel type columns are converted to int."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "channel_id", "name": "Channel", "type": "channel"},
            ],
        )
        value = '[{"channel_id": "789012"}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"channel_id": 789012}]

    def test_table_with_invalid_role_value_removes_key(self) -> None:
        """Test that invalid values in role columns are removed."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role"},
                {"key": "name", "name": "Name"},
            ],
        )
        value = '[{"role_id": "not_a_number", "name": "Test"}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"name": "Test"}]

    def test_table_with_already_int_value(self) -> None:
        """Test that values already int are kept."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role"},
            ],
        )
        # JSON with number already as int
        value = '[{"role_id": 123456}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"role_id": 123456}]

    def test_table_skips_non_dict_rows(self) -> None:
        """Test that rows that are not dict are ignored."""
        option = ConfigOption(
            key="test_table",
            name="Test Table",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "name", "name": "Name"},
            ],
        )
        value = '[{"name": "valid"}, "invalid_row", {"name": "also_valid"}]'

        result = _convert_form_value(value, ConfigOptionType.TABLE, option)

        assert result == [{"name": "valid"}, {"name": "also_valid"}]


class TestConvertFormValueEmbed:
    """Tests for _convert_form_value with EMBED type."""

    def test_embed_valid_json_dict(self) -> None:
        """Test conversion of valid JSON as dictionary."""
        value = '{"title": "My Embed", "color": "#ff0000"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result == {"title": "My Embed", "color": "#ff0000"}

    def test_embed_json_too_large(self) -> None:
        """Test that JSON too large returns None."""
        # Create JSON larger than 100KB
        large_title = "x" * 100_001
        large_value = '{"title": "' + large_title + '"}'
        assert len(large_value) > 100_000

        result = _convert_form_value(large_value, ConfigOptionType.EMBED)
        assert result is None

    def test_embed_invalid_json(self) -> None:
        """Test that invalid JSON returns None."""
        value = "not valid json {"
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result is None

    def test_embed_not_a_dict(self) -> None:
        """Test that JSON that is not a dictionary returns None."""
        value = '["item1", "item2"]'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result is None

    def test_embed_filters_invalid_keys(self) -> None:
        """Test that invalid keys are filtered."""
        value = '{"title": "Test", "invalid_key": "value", "color": "#000"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result == {"title": "Test", "color": "#000"}
        assert "invalid_key" not in result

    def test_embed_with_all_valid_keys(self) -> None:
        """Test that all valid keys are kept."""
        value = """{
            "title": "My Embed",
            "color": "#ff0000",
            "thumbnail_url": "https://example.com/thumb.png",
            "image_url": "https://example.com/image.png",
            "footer_text": "Footer",
            "footer_icon_url": "https://example.com/icon.png",
            "sections": []
        }"""
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result["title"] == "My Embed"
        assert result["color"] == "#ff0000"
        assert result["thumbnail_url"] == "https://example.com/thumb.png"
        assert result["image_url"] == "https://example.com/image.png"
        assert result["footer_text"] == "Footer"
        assert result["footer_icon_url"] == "https://example.com/icon.png"
        assert result["sections"] == []

    def test_embed_sections_not_list_becomes_empty(self) -> None:
        """Test that sections that is not a list becomes empty list."""
        value = '{"title": "Test", "sections": "not a list"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result["sections"] == []

    def test_embed_with_sections(self) -> None:
        """Test embed with sections."""
        value = """{
            "title": "Statistics",
            "sections": [
                {"type": "header", "content": "Information"},
                {"type": "text", "content": "Description"},
                {"type": "progress", "value_key": "health", "max_value": 100}
            ]
        }"""
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result["title"] == "Statistics"
        assert len(result["sections"]) == 3
        assert result["sections"][0]["type"] == "header"
        assert result["sections"][1]["type"] == "text"
        assert result["sections"][2]["type"] == "progress"

    def test_embed_url_empty_after_strip(self) -> None:
        """Test that URL empty after strip is ignored."""
        value = '{"title": "Test", "thumbnail_url": "   "}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        # Should not have thumbnail_url since it's empty after strip
        assert "thumbnail_url" not in result or result.get("thumbnail_url") == "   "

    def test_embed_url_invalid_removed(self) -> None:
        """Test that invalid URL (not placeholder nor http) is removed."""
        value = '{"title": "Test", "thumbnail_url": "invalid_url", "image_url": "https://valid.com/img.png"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        # Invalid URL should be removed
        assert "thumbnail_url" not in result
        # Valid URL should be kept
        assert result["image_url"] == "https://valid.com/img.png"

    def test_embed_url_placeholder_valid(self) -> None:
        """Test that placeholder URL is valid."""
        value = '{"title": "Test", "thumbnail_url": "{user_avatar}"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED)
        assert result["thumbnail_url"] == "{user_avatar}"


class TestConvertFormValueEmbedSections:
    """Tests for _convert_form_value with EMBED_SECTIONS type."""

    def test_embed_sections_list(self) -> None:
        """Test conversion of direct list."""
        value = '[{"type": "text", "content": "Hello"}]'
        result = _convert_form_value(value, ConfigOptionType.EMBED_SECTIONS)
        assert result == [{"type": "text", "content": "Hello"}]

    def test_embed_sections_dict_with_sections_key(self) -> None:
        """Test conversion of dict with 'sections' key."""
        value = '{"sections": [{"type": "text", "content": "Hello"}]}'
        result = _convert_form_value(value, ConfigOptionType.EMBED_SECTIONS)
        assert result == [{"type": "text", "content": "Hello"}]

    def test_embed_sections_not_list(self) -> None:
        """Test that value that is not a list returns None."""
        value = '{"type": "text"}'
        result = _convert_form_value(value, ConfigOptionType.EMBED_SECTIONS)
        assert result is None


class TestConvertFormValueDefault:
    """Tests for _convert_form_value with unknown types."""

    def test_unknown_type_returns_value_as_is(self) -> None:
        """Test that unknown type returns value unchanged."""
        # Use a mock type that doesn't match any case
        from unittest.mock import MagicMock

        unknown_type = MagicMock()
        unknown_type.value = "unknown"
        result = _convert_form_value("test_value", unknown_type)
        assert result == "test_value"


class TestUpdateOptionsBatch:
    """Tests for update_options_batch."""

    async def test_empty_options_returns_early(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that empty options returns without saving."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.json = AsyncMock(return_value={"options": {}})

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch(
                "discord_bot.web.routers.config._render_cog_settings",
                new_callable=AsyncMock,
            ),
        ):
            mock_config_service = MagicMock()
            mock_config_service.set_value = AsyncMock(return_value=(True, None))
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

            # set_value should not be called since options is empty
            mock_config_service.set_value.assert_not_called()

    async def test_invalid_json_raises_400(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that invalid JSON returns 400."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.json = AsyncMock(
            side_effect=json.JSONDecodeError("Invalid JSON", "", 0)
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in exc_info.value.detail

    async def test_invalid_content_type_raises_415(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that invalid Content-Type returns 415."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.headers = {"content-type": "text/plain"}

        with pytest.raises(HTTPException) as exc_info:
            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

        assert exc_info.value.status_code == 415
        assert "Content-Type" in exc_info.value.detail

    async def test_missing_content_type_raises_415(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that missing Content-Type returns 415."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

        assert exc_info.value.status_code == 415
        assert "Content-Type" in exc_info.value.detail

    async def test_option_not_found_adds_error(
        self,
        mock_config_request: MagicMock,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that option not found adds error."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.json = AsyncMock(
            return_value={"options": {"nonexistent_option": "value"}}
        )

        empty_service = ConfigSchemaService()

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=empty_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch(
                "discord_bot.web.routers.config._render_cog_settings",
                new_callable=AsyncMock,
            ) as mock_render,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

            # Should be called with error message
            mock_render.assert_called_once()
            call_kwargs = mock_render.call_args.kwargs
            assert "nonexistent_option" in call_kwargs["error"]

    async def test_successful_batch_save(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test successful batch save."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.json = AsyncMock(
            return_value={"options": {"string_option": "new_value"}}
        )

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch(
                "discord_bot.web.routers.config._notify_cog_config_changed", new_callable=AsyncMock
            ) as mock_notify,
            patch(
                "discord_bot.web.routers.config._render_cog_settings",
                new_callable=AsyncMock,
            ),
        ):
            mock_config_service = MagicMock()
            mock_config_service.set_value = AsyncMock(return_value=(True, None))
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

            # set_value should be called once
            mock_config_service.set_value.assert_called_once()

            # Notify should be called once with the key
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args.kwargs
            assert "string_option" in call_kwargs["keys"]

    async def test_validation_error_adds_to_errors(
        self,
        mock_config_request: MagicMock,
        mock_schema_service: ConfigSchemaService,
        test_user: dict[str, Any],
        test_session: AsyncSession,
    ) -> None:
        """Test that validation error is added to error list."""
        from discord_bot.web.routers.config import update_options_batch

        mock_config_request.json = AsyncMock(return_value={"options": {"string_option": "value"}})

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=mock_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
            patch(
                "discord_bot.web.routers.config._render_cog_settings",
                new_callable=AsyncMock,
            ) as mock_render,
        ):
            mock_config_service = MagicMock()
            mock_config_service.set_value = AsyncMock(return_value=(False, "Validation failed"))
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await update_options_batch(
                mock_config_request,
                111222333,
                "test_cog",
                test_user,
                test_session,
            )

            # Should be called with error message
            mock_render.assert_called_once()
            call_kwargs = mock_render.call_args.kwargs
            assert "Validation failed" in call_kwargs["error"]
