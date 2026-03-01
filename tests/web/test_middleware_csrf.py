"""Tests para el middleware CSRF."""

from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.csrf import (
    CSRF_HEADER_NAME,
    CSRF_TOKEN_KEY,
    get_csrf_token,
)


class TestGetCsrfToken:
    """Tests para get_csrf_token."""

    def test_generates_token_if_not_exists(self) -> None:
        """Probar que genera un token si no existe en la sesión."""
        request = MagicMock(spec=Request)
        request.session = {}

        token = get_csrf_token(request)

        assert token is not None
        assert len(token) > 20
        assert CSRF_TOKEN_KEY in request.session
        assert request.session[CSRF_TOKEN_KEY] == token

    def test_returns_existing_token(self) -> None:
        """Probar que retorna el token existente."""
        request = MagicMock(spec=Request)
        existing_token = "existing-token-123"
        request.session = {CSRF_TOKEN_KEY: existing_token}

        token = get_csrf_token(request)

        assert token == existing_token

    def test_token_is_consistent(self) -> None:
        """Probar que múltiples llamadas retornan el mismo token."""
        request = MagicMock(spec=Request)
        request.session = {}

        token1 = get_csrf_token(request)
        token2 = get_csrf_token(request)

        assert token1 == token2


class TestCSRFMiddleware:
    """Tests unitarios para CSRFMiddleware."""

    def test_is_exempt_returns_true_for_exempt_paths(self) -> None:
        """Probar que _is_exempt retorna True para rutas exentas."""
        from discord_bot.web.middleware.csrf import _is_exempt

        assert _is_exempt("/auth/callback") is True
        assert _is_exempt("/health") is True

    def test_is_exempt_returns_false_for_normal_paths(self) -> None:
        """Probar que _is_exempt retorna False para rutas normales."""
        from discord_bot.web.middleware.csrf import _is_exempt

        assert _is_exempt("/submit") is False
        assert _is_exempt("/guild/123/config") is False


class TestCSRFMiddlewareIntegration:
    """Tests de integración para CSRFMiddleware."""

    @pytest.fixture
    def app_with_csrf(self) -> TestClient:
        """Crear app con CSRF middleware para testing."""
        from fastapi import FastAPI
        from starlette.middleware.sessions import SessionMiddleware

        from discord_bot.web.middleware.csrf import CSRFMiddleware

        app = FastAPI()
        # CSRFMiddleware first, SessionMiddleware after (last added processes first)
        app.add_middleware(CSRFMiddleware)
        app.add_middleware(SessionMiddleware, secret_key="test-secret")

        @app.get("/")
        async def root(request: Request) -> dict[str, str]:
            return {"csrf_token": get_csrf_token(request)}

        @app.post("/submit")
        async def submit() -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/auth/callback")
        async def oauth_callback() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    def test_get_request_passes(self, app_with_csrf: TestClient) -> None:
        """Probar que GET requests pasan sin CSRF."""
        response = app_with_csrf.get("/")
        assert response.status_code == 200

    def test_post_without_token_fails(self, app_with_csrf: TestClient) -> None:
        """Probar que POST sin token CSRF falla."""
        response = app_with_csrf.post("/submit")
        assert response.status_code == 403
        assert "CSRF" in response.text

    def test_post_with_valid_header_token_passes(self, app_with_csrf: TestClient) -> None:
        """Probar que POST con token válido en header pasa."""
        # Primero obtener el token
        get_response = app_with_csrf.get("/")
        csrf_token = get_response.json()["csrf_token"]

        # Luego hacer POST con el token
        response = app_with_csrf.post(
            "/submit",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert response.status_code == 200

    def test_post_with_invalid_token_fails(self, app_with_csrf: TestClient) -> None:
        """Probar que POST con token inválido falla."""
        # Primero obtener una sesión
        app_with_csrf.get("/")

        response = app_with_csrf.post(
            "/submit",
            headers={CSRF_HEADER_NAME: "invalid-token"},
        )
        assert response.status_code == 403

    def test_exempt_path_passes_without_token(self, app_with_csrf: TestClient) -> None:
        """Probar que rutas exentas pasan sin CSRF."""
        response = app_with_csrf.post("/auth/callback")
        assert response.status_code == 200

    def test_post_with_form_token_passes(self, app_with_csrf: TestClient) -> None:
        """Probar que POST con token en formulario pasa."""
        # Primero obtener el token
        get_response = app_with_csrf.get("/")
        csrf_token = get_response.json()["csrf_token"]

        # Luego hacer POST con el token en form data
        response = app_with_csrf.post(
            "/submit",
            data={"csrf_token": csrf_token},
        )
        assert response.status_code == 200

    def test_post_without_session_token_returns_403(self, app_with_csrf: TestClient) -> None:
        """Probar que POST sin token en sesión retorna 403."""
        # Crear un nuevo cliente sin cookies previas para asegurar sesión vacía
        from fastapi import FastAPI
        from starlette.middleware.sessions import SessionMiddleware

        from discord_bot.web.middleware.csrf import CSRFMiddleware

        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        app.add_middleware(SessionMiddleware, secret_key="test-secret")

        @app.post("/submit")
        async def submit() -> dict[str, str]:
            return {"status": "ok"}

        # Crear cliente sin cookies
        from starlette.testclient import TestClient

        client = TestClient(app, cookies={})

        # POST directo sin haber establecido sesión - retorna 403 con mensaje de CSRF
        response = client.post("/submit")
        assert response.status_code == 403
        assert "CSRF" in response.text
