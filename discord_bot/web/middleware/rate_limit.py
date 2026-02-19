"""Middleware de rate limiting para protección contra abuso."""

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Configuración de límites por ruta
RATE_LIMITS: dict[str, tuple[int, int]] = {
    # (requests, window_seconds)
    "/auth/login": (10, 60),  # 10 requests por minuto
    "/auth/callback": (10, 60),  # 10 requests por minuto
}

# Límite por defecto para rutas POST de configuración
DEFAULT_POST_LIMIT = (30, 60)  # 30 requests por minuto


@dataclass
class RateLimitState:
    """Estado de rate limiting para una IP/ruta."""

    requests: list[float] = field(default_factory=list)

    def clean_old_requests(self, window_seconds: int) -> None:
        """Eliminar requests fuera de la ventana de tiempo."""
        cutoff = time.time() - window_seconds
        self.requests = [t for t in self.requests if t > cutoff]

    def is_limited(self, max_requests: int, window_seconds: int) -> bool:
        """Verificar si se excedió el límite."""
        self.clean_old_requests(window_seconds)
        return len(self.requests) >= max_requests

    def add_request(self) -> None:
        """Registrar una nueva request."""
        self.requests.append(time.time())


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware para limitar la tasa de requests.

    Implementa un algoritmo de ventana deslizante simple.
    Los límites se aplican por IP + ruta.
    """

    def __init__(self, app: object) -> None:
        """Inicializar el middleware.

        Args:
            app: Aplicación ASGI
        """
        super().__init__(app)  # type: ignore[arg-type]
        # Estado por (ip, path_pattern)
        self._state: dict[tuple[str, str], RateLimitState] = defaultdict(RateLimitState)
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Obtener IP del cliente considerando proxies."""
        # X-Forwarded-For puede contener múltiples IPs
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Tomar la primera IP (cliente original)
            return forwarded.split(",")[0].strip()

        # X-Real-IP es otra opción común
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback al cliente directo
        if request.client:
            return request.client.host

        return "unknown"

    def _get_path_pattern(self, path: str) -> str:
        """Obtener patrón de ruta para rate limiting.

        Normaliza rutas con IDs variables.
        """
        # Para rutas de config, agrupar por patrón
        parts = path.split("/")
        if len(parts) >= 4 and parts[1] == "guild":
            # /guild/{id}/cog/{name}/... -> /guild/*/cog/*/*
            if len(parts) >= 5 and parts[3] == "cog":
                return (
                    "/guild/*/cog/*/" + "/".join(parts[5:]) if len(parts) > 5 else "/guild/*/cog/*"
                )
        return path

    def _get_limit(self, path: str, method: str) -> tuple[int, int] | None:
        """Obtener límite para una ruta.

        Returns:
            Tuple (max_requests, window_seconds) o None si no hay límite.
        """
        # Verificar límites específicos
        if path in RATE_LIMITS:
            return RATE_LIMITS[path]

        # Aplicar límite por defecto a POSTs en /guild/
        if method == "POST" and path.startswith("/guild/"):
            return DEFAULT_POST_LIMIT

        return None

    def _periodic_cleanup(self) -> None:
        """Limpiar estados antiguos periódicamente."""
        now = time.time()
        # Limpiar cada 5 minutos
        if now - self._last_cleanup < 300:
            return

        self._last_cleanup = now
        # Eliminar estados sin requests recientes (más de 10 minutos)
        keys_to_delete = []
        for key, state in self._state.items():
            state.clean_old_requests(600)
            if not state.requests:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._state[key]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Procesar request aplicando rate limiting."""
        self._periodic_cleanup()

        path = request.url.path
        method = request.method

        limit = self._get_limit(path, method)
        if not limit:
            response: Response = await call_next(request)
            return response

        max_requests, window_seconds = limit
        client_ip = self._get_client_ip(request)
        path_pattern = self._get_path_pattern(path)

        state_key = (client_ip, path_pattern)
        state = self._state[state_key]

        if state.is_limited(max_requests, window_seconds):
            return Response(
                content="Too Many Requests",
                status_code=429,
                headers={"Retry-After": str(window_seconds)},
            )

        state.add_request()
        response = await call_next(request)
        return response
