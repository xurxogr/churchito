"""Tests for browser language detection and i18n integration in config routes."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import ConfigSchemaService
from discord_bot.i18n import get_i18n_service
from discord_bot.web.routers.config import get_browser_language


@pytest.fixture
def mock_schema_service_with_choices() -> ConfigSchemaService:
    """Create schema service with choices and columns options.

    Returns:
        ConfigSchemaService: Schema service with test data
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
                    key="choice_option",
                    name="Choice Option",
                    option_type=ConfigOptionType.TEXT_CHOICE,
                    choices=[
                        ("Blue", "blurple"),
                        ("Green", "green"),
                        ("Red", "red"),
                    ],
                    default="green",
                ),
                ConfigOption(
                    key="table_option",
                    name="Table Option",
                    option_type=ConfigOptionType.TABLE,
                    default=[],
                    columns=[
                        {"key": "from_role", "name": "Source role", "type": "role"},
                        {"key": "to_role", "name": "Target role", "type": "role"},
                    ],
                ),
            ],
        )
    )
    return service


@pytest.fixture
def mock_config_request(simple_app: FastAPI, test_user: dict[str, Any]) -> MagicMock:
    """Create mock request for config.

    Args:
        simple_app: FastAPI application
        test_user: Test user data

    Returns:
        MagicMock: Mock request
    """
    request = MagicMock(spec=Request)
    request.app = simple_app
    request.scope = {"root_path": ""}
    request.headers = {"content-type": "application/json", "Accept-Language": "en"}

    # Mock templates
    request.app.state.templates = MagicMock(spec=Jinja2Templates)
    mock_response = MagicMock()
    request.app.state.templates.TemplateResponse.return_value = mock_response

    # Mock bot with a guild
    mock_guild = MagicMock()
    mock_guild.id = 111222333
    mock_guild.name = "Test Guild"
    mock_guild.text_channels = []
    mock_guild.roles = []
    mock_guild.me = MagicMock()
    mock_guild.me.top_role = MagicMock()
    mock_guild.member_count = 100
    request.app.state.bot = MagicMock()
    request.app.state.bot.get_guild.return_value = mock_guild
    request.app.state.bot.user = MagicMock()
    request.app.state.bot.user.id = 123456789

    return request


class TestGetBrowserLanguage:
    """Tests for get_browser_language function."""

    def test_returns_english_for_en_header(self) -> None:
        """Test that it returns 'en' for English Accept-Language."""
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "en-US,en;q=0.9"}
        result = get_browser_language(request)
        assert result == "en"

    def test_returns_spanish_for_es_header(self) -> None:
        """Test that it returns 'es' for Spanish Accept-Language."""
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
        result = get_browser_language(request)
        assert result == "es"

    def test_returns_spanish_for_es_mx_header(self) -> None:
        """Test that it returns 'es' for Mexican Spanish Accept-Language."""
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "es-MX,es;q=0.9"}
        result = get_browser_language(request)
        assert result == "es"

    def test_returns_default_for_unsupported_language(self) -> None:
        """Test that it returns default language for unsupported languages."""
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "fr-FR,fr;q=0.9,de;q=0.8"}
        result = get_browser_language(request)
        assert result == "en"

    def test_returns_default_for_empty_header(self) -> None:
        """Test that it returns default language for empty header."""
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": ""}
        result = get_browser_language(request)
        assert result == "en"

    def test_returns_default_for_missing_header(self) -> None:
        """Test that it returns default language when header is missing."""
        request = MagicMock(spec=Request)
        request.headers = {}
        result = get_browser_language(request)
        assert result == "en"

    def test_handles_complex_accept_language(self) -> None:
        """Test handling of complex Accept-Language header with quality factors."""
        request = MagicMock(spec=Request)
        # Spanish has highest priority (implicit q=1.0)
        request.headers = {"Accept-Language": "es,en;q=0.9,fr;q=0.8"}
        result = get_browser_language(request)
        assert result == "es"

    def test_first_supported_language_wins(self) -> None:
        """Test that first supported language in header is used."""
        request = MagicMock(spec=Request)
        # German first (unsupported), then Spanish (supported)
        request.headers = {"Accept-Language": "de,es;q=0.9,en;q=0.8"}
        result = get_browser_language(request)
        assert result == "es"


class TestI18nIntegration:
    """Tests for i18n integration in config routes."""

    def test_i18n_service_available(self) -> None:
        """Test that i18n service is available."""
        i18n = get_i18n_service()
        assert i18n is not None
        assert "en" in i18n.SUPPORTED_LANGUAGES
        assert "es" in i18n.SUPPORTED_LANGUAGES

    def test_translate_ui_string(self) -> None:
        """Test translating UI strings."""
        i18n = get_i18n_service()

        # English
        result_en = i18n.translate("ui.nav.dashboard", "en")
        assert result_en == "Dashboard"

        # Spanish
        result_es = i18n.translate("ui.nav.dashboard", "es")
        assert result_es == "Panel"

    def test_translate_cog_display_name(self) -> None:
        """Test translating cog display names."""
        i18n = get_i18n_service()

        # English
        result_en = i18n.translate("cogs.verification.display_name", "en")
        assert result_en == "Verification"

        # Spanish
        result_es = i18n.translate("cogs.verification.display_name", "es")
        assert result_es == "Verificación"

    def test_translate_config_option(self) -> None:
        """Test translating config option names."""
        i18n = get_i18n_service()

        opt_trans = i18n.get_option_translation("verification", "verify_button_text", "es")
        assert opt_trans.get("name") == "Texto botón verificar"
        assert opt_trans.get("default") == "Verificar"


class TestCogSettingsWithChoicesAndColumns:
    """Tests for _render_cog_settings with choices and columns translation."""

    @pytest.fixture
    def purge_schema_service(self) -> ConfigSchemaService:
        """Create schema service with the real purge schema (has choices and columns).

        Returns:
            ConfigSchemaService: Schema service with purge schema
        """
        from discord_bot.purge.config import PURGE_CONFIG_SCHEMA

        service = ConfigSchemaService()
        service.register_schema(PURGE_CONFIG_SCHEMA)
        return service

    @pytest.mark.asyncio
    async def test_cog_settings_translates_choices_to_spanish(
        self,
        mock_config_request: MagicMock,
        purge_schema_service: ConfigSchemaService,
    ) -> None:
        """Test that choices are translated to Spanish in cog_settings."""
        from discord_bot.web.routers.config import cog_settings

        session = AsyncMock(spec=AsyncSession)

        # Set Accept-Language to Spanish
        mock_config_request.headers = {
            "content-type": "application/json",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

        user = {"id": "123456789", "username": "testuser"}

        # Setup mock guild
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_guild.member_count = 100
        mock_guild.get_member.return_value = None
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=purge_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "purge", user, session)

            # Verify TemplateResponse was called
            mock_config_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            # Find mod_button_color option which has choices
            options = context["options"]
            button_color_opt = next((o for o in options if o["key"] == "mod_button_color"), None)
            assert button_color_opt is not None
            assert button_color_opt["choices"] is not None
            # Verify Spanish translations were applied
            choice_labels = [c[0] for c in button_color_opt["choices"]]
            assert "Azul" in choice_labels  # Blue -> Azul
            assert "Verde" in choice_labels  # Green -> Verde
            assert "Rojo" in choice_labels  # Red -> Rojo

    @pytest.mark.asyncio
    async def test_cog_settings_translates_columns_to_spanish(
        self,
        mock_config_request: MagicMock,
        purge_schema_service: ConfigSchemaService,
    ) -> None:
        """Test that table columns are translated to Spanish in cog_settings."""
        from discord_bot.web.routers.config import cog_settings

        session = AsyncMock(spec=AsyncSession)

        # Set Accept-Language to Spanish
        mock_config_request.headers = {
            "content-type": "application/json",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

        user = {"id": "123456789", "username": "testuser"}

        # Setup mock guild
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_guild.member_count = 100
        mock_guild.get_member.return_value = None
        mock_config_request.app.state.bot.get_guild.return_value = mock_guild
        mock_config_request.app.state.bot.get_cog.return_value = None

        with (
            patch(
                "discord_bot.web.routers.config.get_config_schema_service",
                return_value=purge_schema_service,
            ),
            patch("discord_bot.web.routers.config.ConfigService") as mock_config_service_class,
        ):
            mock_config_service = MagicMock()
            mock_config_service.get_all_config = AsyncMock(return_value={})
            mock_config_service.is_cog_enabled = AsyncMock(return_value=True)
            mock_config_service_class.return_value = mock_config_service

            await cog_settings(mock_config_request, 111222333, "purge", user, session)

            # Verify TemplateResponse was called
            call_kwargs = mock_config_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]

            # Find war_promotions option which has columns
            options = context["options"]
            promotions_opt = next((o for o in options if o["key"] == "war_promotions"), None)
            assert promotions_opt is not None
            assert promotions_opt["columns"] is not None
            assert len(promotions_opt["columns"]) == 2
            # Verify Spanish translations were applied
            col_names = [c["name"] for c in promotions_opt["columns"]]
            assert "Rol origen" in col_names  # Source role -> Rol origen
            assert "Rol destino" in col_names  # Target role -> Rol destino
