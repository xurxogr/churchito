"""Tests for the web application."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from discord_bot.common.core import AppSettings
from discord_bot.web.app import create_app


class TestCreateApp:
    """Tests for create_app."""

    def test_creates_fastapi_app(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test that it creates a FastAPI application."""
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
        """Test that it creates application without bot."""
        app = create_app(test_app_settings, mock_db_service)

        assert app is not None
        assert app.state.bot is None

    def test_generates_secret_key_if_not_set(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Test that it generates secret_key if not configured."""
        test_app_settings.web.secret_key = ""

        with patch("discord_bot.web.app.logger") as mock_logger:
            app = create_app(test_app_settings, mock_db_service)

            assert app is not None
            # Verify warning was logged
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
        """Test that it includes routers."""
        app = create_app(test_app_settings, mock_db_service)

        # Verify routes are registered
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/auth/login" in routes or any("/auth" in r for r in routes)

    def test_health_check_endpoint(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Test the health check endpoint."""
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
        """Test the HTTP exception handler with protected route."""
        from fastapi import HTTPException

        app = create_app(test_app_settings, mock_db_service)

        # Add a route that raises HTTPException
        @app.get("/test-http-error")
        async def raise_http_error() -> None:
            raise HTTPException(status_code=403, detail="Test error")

        client = TestClient(app)
        response = client.get("/test-http-error")

        assert response.status_code == 403
        assert "text/html" in response.headers.get("content-type", "")
        # 4xx error details are shown
        assert "Test error" in response.text

    def test_http_exception_handler_hides_5xx_details(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Test that 5xx errors don't expose internal details."""
        from fastapi import HTTPException

        app = create_app(test_app_settings, mock_db_service)

        @app.get("/test-server-error")
        async def raise_server_error() -> None:
            raise HTTPException(status_code=500, detail="Database connection failed: host=secret")

        client = TestClient(app)
        response = client.get("/test-server-error")

        assert response.status_code == 500
        # Should not expose technical details
        assert "Database" not in response.text
        assert "secret" not in response.text
        # Should show generic message
        assert "Internal server error" in response.text

    def test_generic_exception_handler(
        self,
        test_app_settings: AppSettings,
        mock_db_service: MagicMock,
    ) -> None:
        """Test that unhandled exceptions don't expose details."""
        app = create_app(test_app_settings, mock_db_service)

        @app.get("/test-unhandled")
        async def raise_unhandled() -> None:
            raise ValueError("Sensitive internal error with secrets")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-unhandled")

        assert response.status_code == 500
        # Should not expose internal error
        assert "Sensitive" not in response.text
        assert "secrets" not in response.text
        # Should show generic message
        assert "Internal server error" in response.text
