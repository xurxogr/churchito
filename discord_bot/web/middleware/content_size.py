"""Middleware para limitar el tamaño del body de las requests."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Límite por defecto: 1MB (suficiente para JSON de configuración)
DEFAULT_MAX_BODY_SIZE = 1 * 1024 * 1024


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware que limita el tamaño máximo del body de las requests.

    Previene ataques de denegación de servicio por envío de bodies muy grandes.
    Verifica el header Content-Length antes de procesar la request.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = DEFAULT_MAX_BODY_SIZE) -> None:
        """Inicializar middleware.

        Args:
            app (ASGIApp): Aplicación ASGI
            max_body_size (int): Tamaño máximo en bytes (default: 1MB)
        """
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Procesar request verificando el tamaño del body.

        Args:
            request (Request): Request entrante
            call_next (Callable[[Request], Awaitable[Response]]): Siguiente handler

        Returns:
            Response: Respuesta del handler o error 413
        """
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                size = int(content_length)
                if size > self.max_body_size:
                    return Response(
                        content="Request body too large",
                        status_code=413,
                        headers={"Content-Type": "text/plain"},
                    )
            except ValueError:
                # Content-Length inválido, dejar que falle más adelante
                pass

        response: Response = await call_next(request)
        return response
