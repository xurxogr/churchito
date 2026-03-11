"""Middleware para añadir headers de seguridad HTTP."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Content Security Policy
# - default-src 'self': Solo recursos del mismo origen por defecto
# - script-src: Scripts del mismo origen + inline (necesario para HTMX)
# - style-src: Estilos del mismo origen + inline (necesario para Tailwind)
# - img-src: Imágenes del mismo origen + Discord CDN + data URIs
# - font-src: Fuentes del mismo origen
# - connect-src: Conexiones XHR/fetch al mismo origen
# - frame-ancestors 'none': Equivalente a X-Frame-Options: DENY
# - base-uri 'self': Restringe <base> tag
# - form-action 'self': Formularios solo al mismo origen
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https://cdn.discordapp.com https://media.discordapp.net data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# HSTS: 1 año, incluir subdominios
DEFAULT_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware que añade headers de seguridad HTTP a todas las respuestas.

    Headers añadidos:
    - X-Frame-Options: Previene clickjacking
    - X-Content-Type-Options: Previene MIME sniffing
    - Referrer-Policy: Controla información de referrer
    - Content-Security-Policy: Controla recursos permitidos
    - Strict-Transport-Security: Fuerza HTTPS (solo si https_only=True)
    """

    def __init__(self, app: ASGIApp, https_only: bool = True) -> None:
        """Inicializar middleware.

        Args:
            app (ASGIApp): Aplicación ASGI
            https_only (bool): Si True, añade header HSTS
        """
        super().__init__(app)
        self.https_only = https_only

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Procesar request añadiendo headers de seguridad a la respuesta.

        Args:
            request (Request): Request entrante
            call_next (Callable[[Request], Awaitable[Response]]): Siguiente handler

        Returns:
            Response: Respuesta con headers de seguridad añadidos
        """
        response: Response = await call_next(request)

        # Prevenir clickjacking (redundante con CSP frame-ancestors, pero para navegadores antiguos)
        response.headers["X-Frame-Options"] = "DENY"

        # Prevenir MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Controlar información de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = DEFAULT_CSP

        # HSTS solo si está configurado para HTTPS
        if self.https_only:
            response.headers["Strict-Transport-Security"] = DEFAULT_HSTS

        return response
