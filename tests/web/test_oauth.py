"""Tests para OAuth."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.auth.oauth import router


@pytest.fixture
def oauth_app(simple_app: FastAPI) -> FastAPI:
    """Crear aplicación con router OAuth.

    Args:
        simple_app (FastAPI): Aplicación base

    Returns:
        FastAPI: Aplicación con OAuth
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def oauth_client(oauth_app: FastAPI) -> TestClient:
    """Crear cliente para OAuth.

    Args:
        oauth_app (FastAPI): Aplicación

    Returns:
        TestClient: Cliente de prueba
    """
    return TestClient(oauth_app)


class TestLogin:
    """Tests para el endpoint de login."""

    def test_login_redirects_to_discord(self, oauth_client: TestClient) -> None:
        """Probar que login redirige a Discord."""
        response = oauth_client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 307
        assert "discord.com" in response.headers["location"]

    def test_login_without_client_id_fails(
        self, oauth_app: FastAPI, oauth_client: TestClient
    ) -> None:
        """Probar que login falla sin client_id."""
        oauth_app.state.settings.web.client_id = None

        response = oauth_client.get("/auth/login")
        assert response.status_code == 500


class TestCallback:
    """Tests para el endpoint de callback."""

    def test_callback_with_error_redirects(self, oauth_client: TestClient) -> None:
        """Probar que callback con error redirige a login."""
        response = oauth_client.get("/auth/callback?error=access_denied", follow_redirects=False)

        assert response.status_code == 307
        assert "error=oauth_denied" in response.headers["location"]

    def test_callback_without_code_redirects(self, oauth_client: TestClient) -> None:
        """Probar que callback sin código redirige a login."""
        response = oauth_client.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 307
        assert "error=no_code" in response.headers["location"]

    def test_callback_with_invalid_state_redirects(self, oauth_client: TestClient) -> None:
        """Probar que callback con estado inválido redirige a login."""
        response = oauth_client.get(
            "/auth/callback?code=test&state=invalid", follow_redirects=False
        )

        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]


class TestLogout:
    """Tests para el endpoint de logout."""

    def test_logout_clears_session(self, oauth_client: TestClient) -> None:
        """Probar que logout limpia la sesión."""
        response = oauth_client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "/"


class TestCallbackStateValidation:
    """Tests para validación del state en callback."""

    def test_callback_validates_state(self, oauth_client: TestClient) -> None:
        """Probar que callback valida el state correctamente."""
        # Sin state previo en sesión, cualquier state es inválido
        response = oauth_client.get(
            "/auth/callback?code=test&state=any_state", follow_redirects=False
        )
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]

    def test_callback_missing_state_fails(self, oauth_client: TestClient) -> None:
        """Probar que callback sin state falla."""
        response = oauth_client.get("/auth/callback?code=test", follow_redirects=False)
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]
