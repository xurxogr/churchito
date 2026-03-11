"""Tests para el middleware de límite de tamaño de contenido."""

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.content_size import (
    DEFAULT_MAX_BODY_SIZE,
    ContentSizeLimitMiddleware,
)


class TestContentSizeLimitMiddleware:
    """Tests de integración para ContentSizeLimitMiddleware."""

    @pytest.fixture
    def app_with_size_limit(self) -> TestClient:
        """Crear app con ContentSizeLimitMiddleware (límite por defecto 1MB)."""
        app = FastAPI()
        app.add_middleware(ContentSizeLimitMiddleware)

        @app.get("/")
        async def root(request: Request) -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/submit")
        async def submit(request: Request) -> dict[str, str]:
            await request.body()
            return {"status": "ok"}

        return TestClient(app)

    @pytest.fixture
    def app_with_small_limit(self) -> TestClient:
        """Crear app con límite pequeño (1KB) para testing."""
        app = FastAPI()
        app.add_middleware(ContentSizeLimitMiddleware, max_body_size=1024)

        @app.post("/submit")
        async def submit(request: Request) -> dict[str, str]:
            await request.body()
            return {"status": "ok"}

        return TestClient(app)

    def test_get_request_passes(self, app_with_size_limit: TestClient) -> None:
        """Probar que GET requests pasan sin verificación de tamaño."""
        response = app_with_size_limit.get("/")
        assert response.status_code == 200

    def test_small_body_passes(self, app_with_size_limit: TestClient) -> None:
        """Probar que body pequeño pasa."""
        response = app_with_size_limit.post(
            "/submit",
            content=b"small body",
            headers={"Content-Length": "10"},
        )
        assert response.status_code == 200

    def test_large_body_rejected(self, app_with_small_limit: TestClient) -> None:
        """Probar que body mayor al límite es rechazado."""
        large_body = b"x" * 2048  # 2KB, mayor que el límite de 1KB
        response = app_with_small_limit.post(
            "/submit",
            content=large_body,
            headers={"Content-Length": str(len(large_body))},
        )
        assert response.status_code == 413
        assert "too large" in response.text.lower()

    def test_body_at_limit_passes(self, app_with_small_limit: TestClient) -> None:
        """Probar que body exactamente en el límite pasa."""
        body = b"x" * 1024  # Exactamente 1KB
        response = app_with_small_limit.post(
            "/submit",
            content=body,
            headers={"Content-Length": str(len(body))},
        )
        assert response.status_code == 200

    def test_missing_content_length_passes(self, app_with_small_limit: TestClient) -> None:
        """Probar que request sin Content-Length pasa (chunked encoding)."""
        # TestClient siempre añade Content-Length, pero verificamos el comportamiento
        response = app_with_small_limit.post("/submit", content=b"data")
        assert response.status_code == 200

    def test_invalid_content_length_passes(self, app_with_small_limit: TestClient) -> None:
        """Probar que Content-Length inválido no causa error."""
        response = app_with_small_limit.post(
            "/submit",
            content=b"data",
            headers={"Content-Length": "not-a-number"},
        )
        # Puede pasar o fallar dependiendo del servidor, pero no debería crashear
        assert response.status_code in (200, 400)

    def test_default_limit_is_1mb(self) -> None:
        """Probar que el límite por defecto es 1MB."""
        assert DEFAULT_MAX_BODY_SIZE == 1 * 1024 * 1024
