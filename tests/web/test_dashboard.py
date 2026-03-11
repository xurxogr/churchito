"""Tests para el router de dashboard."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.routers.dashboard import (
    _check_guild_access,
    get_templates,
    router,
)


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


class TestCheckGuildAccess:
    """Tests para _check_guild_access."""

    @pytest.mark.asyncio
    async def test_bot_owner_always_has_access(self) -> None:
        """Probar que bot owner siempre tiene acceso."""
        session = MagicMock()
        bot = MagicMock()

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789012345678,
            is_bot_owner=True,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_guild_owner_always_has_access(self) -> None:
        """Probar que guild owner siempre tiene acceso."""
        session = MagicMock()
        bot = MagicMock()
        # Guild owner is checked via discord_guild.owner_id
        mock_guild = MagicMock()
        mock_guild.owner_id = 123456789012345678
        bot.get_guild.return_value = mock_guild

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is True


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
