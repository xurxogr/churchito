"""Middleware CSRF para protección contra Cross-Site Request Forgery."""

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSRF_TOKEN_KEY = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"

# Rutas exentas de verificación CSRF
EXEMPT_PATHS = frozenset(
    {
        "/auth/callback",  # OAuth callback necesita permitir POST sin CSRF
        "/health",
    }
)

# Métodos que requieren verificación CSRF
UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def get_csrf_token(request: Request) -> str:
    """Obtener o generar el token CSRF de la sesión.

    Args:
        request (Request): Request de Starlette

    Returns:
        str: Token CSRF
    """
    if CSRF_TOKEN_KEY not in request.session:
        request.session[CSRF_TOKEN_KEY] = secrets.token_urlsafe(32)
    token: str = request.session[CSRF_TOKEN_KEY]
    return token


def _is_exempt(path: str) -> bool:
    """Verificar si una ruta está exenta de CSRF.

    Args:
        path (str): Ruta de la request

    Returns:
        bool: True si está exenta
    """
    return path in EXEMPT_PATHS


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware para protección CSRF.

    Genera un token CSRF por sesión y lo valida en requests POST/PUT/DELETE.
    El token puede enviarse como:
    - Header X-CSRF-Token (para HTMX/fetch)
    - Campo de formulario csrf_token
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Procesar la request verificando CSRF si es necesario.

        Args:
            request (Request): Request entrante
            call_next (Callable[[Request], Awaitable[Response]]): Siguiente handler

        Returns:
            Response: Respuesta del handler o error 403
        """
        # Generar token si no existe (para que esté disponible en templates)
        get_csrf_token(request)

        # Solo verificar en métodos unsafe
        if request.method not in UNSAFE_METHODS:
            response: Response = await call_next(request)
            return response

        # Verificar si la ruta está exenta
        if _is_exempt(request.url.path):
            response = await call_next(request)
            return response

        # Obtener token esperado de la sesión
        expected_token = request.session.get(CSRF_TOKEN_KEY)
        if not expected_token:
            return Response(content="CSRF token missing from session", status_code=403)

        # Buscar token en header (preferido para HTMX/fetch)
        submitted_token: str | None = request.headers.get(CSRF_HEADER_NAME)

        # Si no está en header, buscar en form data
        if not submitted_token:
            # Necesitamos leer el body para obtener form data
            # Esto solo funciona si el content-type es form-urlencoded
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                form_value = form.get(CSRF_FORM_FIELD)
                if isinstance(form_value, str):
                    submitted_token = form_value

        # Validar token
        if not submitted_token or not secrets.compare_digest(submitted_token, expected_token):
            return Response(content="CSRF token validation failed", status_code=403)

        response = await call_next(request)
        return response
