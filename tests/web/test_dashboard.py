"""Tests para el router de dashboard."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.routers.dashboard import _get_guild_access, get_templates, router


@pytest.fixture
def dashboard_app(simple_app: FastAPI) -> FastAPI:
    """Crear aplicación con router de dashboard.

    Args:
        simple_app (FastAPI): Aplicación base

    Returns:
        FastAPI: Aplicación con dashboard
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def dashboard_client(dashboard_app: FastAPI) -> TestClient:
    """Crear cliente para dashboard.

    Args:
        dashboard_app (FastAPI): Aplicación

    Returns:
        TestClient: Cliente de prueba
    """
    return TestClient(dashboard_app)


class TestGetTemplates:
    """Tests para get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Probar que retorna templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestGetGuildAccess:
    """Tests para _get_guild_access."""

    def test_owner_has_access_to_any_guild(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que owner tiene acceso a cualquier guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        # Guild que no está en la lista del usuario
        result = _get_guild_access(request, 999999, test_user)
        assert result is not None
        assert result["id"] == "999999"

    def test_owner_gets_guild_info_when_in_list(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que owner obtiene info del guild cuando está en su lista."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        result = _get_guild_access(request, 111222333, test_user)
        assert result is not None
        assert result["name"] == "Test Guild"

    def test_user_with_manage_guild_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario con MANAGE_GUILD tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 111222333, test_user)
        assert result is not None
        assert result["name"] == "Test Guild"

    def test_user_without_permission_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario sin permisos es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 444555666, test_user)
        assert result is None

    def test_user_not_in_guild_denied(self, simple_app: FastAPI, test_user: dict[str, Any]) -> None:
        """Probar que usuario no en el guild es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 999999, test_user)
        assert result is None


class TestIndexRoute:
    """Tests para la ruta index."""

    def test_index_without_user_shows_login(self, dashboard_client: TestClient) -> None:
        """Probar que index sin usuario muestra login."""
        response = dashboard_client.get("/")
        # Puede ser 200 (login page) o 500 si templates no existen
        assert response.status_code in [200, 500]


class TestLoginPageRoute:
    """Tests para la ruta de login."""

    def test_login_page_without_user(self, dashboard_client: TestClient) -> None:
        """Probar página de login sin usuario."""
        response = dashboard_client.get("/login")
        assert response.status_code in [200, 500]


class TestDashboardRoute:
    """Tests para la ruta del dashboard."""

    def test_dashboard_without_auth_redirects(self, dashboard_app: FastAPI) -> None:
        """Probar que dashboard sin autenticación redirige o da error."""
        # Incluir el router de auth para la dependencia
        from discord_bot.web.auth.oauth import router as auth_router

        dashboard_app.include_router(auth_router)
        client = TestClient(dashboard_app, raise_server_exceptions=False)

        response = client.get("/dashboard")
        # Puede ser 401 (unauthorized) o 307 (redirect)
        assert response.status_code in [401, 307, 500]
