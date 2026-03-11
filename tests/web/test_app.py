"""Tests para la aplicación web."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

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

    def test_health_check_endpoint(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar el endpoint de health check."""
        app = create_app(test_app_settings, mock_db_service)
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_http_exception_handler(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar el manejador de excepciones HTTP con ruta protegida."""
        from fastapi import HTTPException

        app = create_app(test_app_settings, mock_db_service)

        # Agregar una ruta que lanza HTTPException
        @app.get("/test-http-error")
        async def raise_http_error() -> None:
            raise HTTPException(status_code=403, detail="Test error")

        client = TestClient(app)
        response = client.get("/test-http-error")

        assert response.status_code == 403
        assert "text/html" in response.headers.get("content-type", "")
        # El detalle de errores 4xx sí se muestra
        assert "Test error" in response.text

    def test_http_exception_handler_hides_5xx_details(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar que errores 5xx no exponen detalles internos."""
        from fastapi import HTTPException

        app = create_app(test_app_settings, mock_db_service)

        @app.get("/test-server-error")
        async def raise_server_error() -> None:
            raise HTTPException(status_code=500, detail="Database connection failed: host=secret")

        client = TestClient(app)
        response = client.get("/test-server-error")

        assert response.status_code == 500
        # No debe exponer el detalle técnico
        assert "Database" not in response.text
        assert "secret" not in response.text
        # Debe mostrar mensaje genérico
        assert "Error interno" in response.text

    def test_generic_exception_handler(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Probar que excepciones no manejadas no exponen detalles."""
        app = create_app(test_app_settings, mock_db_service)

        @app.get("/test-unhandled")
        async def raise_unhandled() -> None:
            raise ValueError("Sensitive internal error with secrets")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-unhandled")

        assert response.status_code == 500
        # No debe exponer el error interno
        assert "Sensitive" not in response.text
        assert "secrets" not in response.text
        # Debe mostrar mensaje genérico
        assert "Error interno" in response.text
