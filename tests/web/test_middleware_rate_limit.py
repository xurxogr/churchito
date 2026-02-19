"""Tests para el middleware de rate limiting."""

import time
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.rate_limit import RateLimitMiddleware, RateLimitState


class TestRateLimitState:
    """Tests para RateLimitState."""

    def test_clean_old_requests(self) -> None:
        """Probar limpieza de requests antiguas."""
        state = RateLimitState()
        now = time.time()

        # Añadir requests: algunas viejas, algunas nuevas
        state.requests = [now - 120, now - 90, now - 30, now - 10]

        state.clean_old_requests(window_seconds=60)

        # Solo deben quedar las de los últimos 60 segundos
        assert len(state.requests) == 2

    def test_is_limited_under_limit(self) -> None:
        """Probar que no está limitado cuando está bajo el límite."""
        state = RateLimitState()
        now = time.time()
        state.requests = [now - 10, now - 5]

        assert state.is_limited(max_requests=5, window_seconds=60) is False

    def test_is_limited_at_limit(self) -> None:
        """Probar que está limitado cuando alcanza el límite."""
        state = RateLimitState()
        now = time.time()
        state.requests = [now - 10, now - 8, now - 6, now - 4, now - 2]

        assert state.is_limited(max_requests=5, window_seconds=60) is True

    def test_add_request(self) -> None:
        """Probar que añade una request."""
        state = RateLimitState()
        assert len(state.requests) == 0

        state.add_request()

        assert len(state.requests) == 1
        assert state.requests[0] <= time.time()


class TestRateLimitMiddleware:
    """Tests para RateLimitMiddleware."""

    def test_get_client_ip_from_forwarded_for(self) -> None:
        """Probar obtención de IP desde X-Forwarded-For."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1"}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_from_real_ip(self) -> None:
        """Probar obtención de IP desde X-Real-IP."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {"x-real-ip": "192.168.1.2"}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.2"

    def test_get_client_ip_from_client(self) -> None:
        """Probar obtención de IP desde client."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.3"

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.3"

    def test_get_client_ip_fallback(self) -> None:
        """Probar fallback a 'unknown' cuando no hay IP."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "unknown"

    def test_get_path_pattern_normalizes_guild_routes(self) -> None:
        """Probar normalización de rutas de guild."""
        middleware = RateLimitMiddleware(MagicMock())

        pattern = middleware._get_path_pattern("/guild/123/cog/test/toggle")

        assert pattern == "/guild/*/cog/*/toggle"

    def test_get_path_pattern_preserves_other_routes(self) -> None:
        """Probar que otras rutas no se modifican."""
        middleware = RateLimitMiddleware(MagicMock())

        pattern = middleware._get_path_pattern("/auth/login")

        assert pattern == "/auth/login"

    def test_get_limit_for_auth_login(self) -> None:
        """Probar límite para /auth/login."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/auth/login", "GET")

        assert limit == (10, 60)

    def test_get_limit_for_post_guild(self) -> None:
        """Probar límite por defecto para POST en guild."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/guild/123/cog/test/toggle", "POST")

        assert limit == (30, 60)

    def test_get_limit_returns_none_for_unprotected(self) -> None:
        """Probar que retorna None para rutas sin límite."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/dashboard", "GET")

        assert limit is None

    def test_periodic_cleanup_removes_old_states(self) -> None:
        """Probar que periodic cleanup elimina estados antiguos."""
        middleware = RateLimitMiddleware(MagicMock())

        # Añadir estado con requests antiguas
        state = RateLimitState()
        state.requests = [time.time() - 700]  # Más de 10 minutos
        middleware._state[("192.168.1.1", "/auth/login")] = state

        # Forzar cleanup estableciendo _last_cleanup hace más de 5 minutos
        middleware._last_cleanup = time.time() - 400

        middleware._periodic_cleanup()

        # El estado debe haber sido eliminado
        assert ("192.168.1.1", "/auth/login") not in middleware._state

    def test_periodic_cleanup_keeps_recent_states(self) -> None:
        """Probar que periodic cleanup mantiene estados recientes."""
        middleware = RateLimitMiddleware(MagicMock())

        # Añadir estado con requests recientes
        state = RateLimitState()
        state.requests = [time.time() - 30]  # 30 segundos
        middleware._state[("192.168.1.1", "/auth/login")] = state

        # Forzar cleanup
        middleware._last_cleanup = time.time() - 400

        middleware._periodic_cleanup()

        # El estado debe mantenerse
        assert ("192.168.1.1", "/auth/login") in middleware._state


class TestRateLimitMiddlewareIntegration:
    """Tests de integración para RateLimitMiddleware."""

    @pytest.fixture
    def app_with_rate_limit(self) -> TestClient:
        """Crear app con rate limit middleware para testing."""
        from fastapi import FastAPI

        from discord_bot.web.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.get("/auth/login")
        async def login() -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/guild/123/cog/test/toggle")
        async def toggle() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/unprotected")
        async def unprotected() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    def test_allows_requests_under_limit(self, app_with_rate_limit: TestClient) -> None:
        """Probar que permite requests bajo el límite."""
        for _ in range(5):
            response = app_with_rate_limit.get("/auth/login")
            assert response.status_code == 200

    def test_blocks_requests_over_limit(self, app_with_rate_limit: TestClient) -> None:
        """Probar que bloquea requests sobre el límite."""
        # Hacer 10 requests (el límite)
        for _ in range(10):
            app_with_rate_limit.get("/auth/login")

        # La siguiente debe ser bloqueada
        response = app_with_rate_limit.get("/auth/login")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_unprotected_routes_not_limited(self, app_with_rate_limit: TestClient) -> None:
        """Probar que rutas sin límite no son afectadas."""
        for _ in range(50):
            response = app_with_rate_limit.get("/unprotected")
            assert response.status_code == 200
