"""Tests para la aplicación web."""

from unittest.mock import MagicMock, patch

from discord_bot.common.core import AppSettings
from discord_bot.web.app import create_app


class TestCreateApp:
    """Tests para create_app."""

    def test_creates_fastapi_app(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
        mock_bot: MagicMock,
    ) -> None:
        """Probar que crea una aplicación FastAPI."""
        app = create_app(test_app_settings, mock_db_service, mock_bot)

        assert app is not None
        assert app.title == "Bot Dashboard"
        assert app.state.settings == test_app_settings
        assert app.state.db_service == mock_db_service
        assert app.state.bot == mock_bot

    def test_creates_app_without_bot(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar que crea aplicación sin bot."""
        app = create_app(test_app_settings, mock_db_service)

        assert app is not None
        assert app.state.bot is None

    def test_generates_secret_key_if_not_set(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar que genera secret_key si no está configurada."""
        test_app_settings.web.secret_key = ""

        with patch("discord_bot.web.app.logger") as mock_logger:
            app = create_app(test_app_settings, mock_db_service)

            assert app is not None
            # Verificar que se registró la advertencia
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "WEB__SECRET_KEY" in str(call)
            ]
            assert len(warning_calls) > 0

    def test_includes_routers(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar que incluye los routers."""
        app = create_app(test_app_settings, mock_db_service)

        # Verificar que hay rutas registradas
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/auth/login" in routes or any("/auth" in r for r in routes)
