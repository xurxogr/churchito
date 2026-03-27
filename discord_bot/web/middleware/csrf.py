"""CSRF middleware for Cross-Site Request Forgery protection."""

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSRF_TOKEN_KEY = "csrf_token"  # noqa: S105 - Key name, not a secret
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"

# Routes exempt from CSRF verification
EXEMPT_PATHS = frozenset(
    {
        "/auth/callback",  # OAuth callback needs to allow POST without CSRF
        "/health",
    }
)

# Methods that require CSRF verification
UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def get_csrf_token(request: Request) -> str:
    """Get or generate the CSRF token from the session.

    Args:
        request (Request): Starlette request

    Returns:
        str: CSRF token
    """
    if CSRF_TOKEN_KEY not in request.session:
        request.session[CSRF_TOKEN_KEY] = secrets.token_urlsafe(32)
    token: str = request.session[CSRF_TOKEN_KEY]
    return token


def _is_exempt(path: str) -> bool:
    """Check if a route is exempt from CSRF.

    Args:
        path (str): Request path

    Returns:
        bool: True if exempt
    """
    return path in EXEMPT_PATHS


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware for CSRF protection.

    Generates a CSRF token per session and validates it on POST/PUT/DELETE requests.
    The token can be sent as:
    - Header X-CSRF-Token (for HTMX/fetch)
    - Form field csrf_token
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request by verifying CSRF if necessary.

        Args:
            request (Request): Incoming request
            call_next (Callable[[Request], Awaitable[Response]]): Next handler

        Returns:
            Response: Handler response or 403 error
        """
        # Generate token if it doesn't exist (so it's available in templates)
        get_csrf_token(request)

        # Only verify on unsafe methods
        if request.method not in UNSAFE_METHODS:
            response: Response = await call_next(request)
            return response

        # Check if the route is exempt
        if _is_exempt(request.url.path):
            response = await call_next(request)
            return response

        # Get expected token from session
        expected_token = request.session.get(CSRF_TOKEN_KEY)
        if not expected_token:
            return Response(content="CSRF token missing from session", status_code=403)

        # Look for token in header (preferred for HTMX/fetch)
        submitted_token: str | None = request.headers.get(CSRF_HEADER_NAME)

        # If not in header, look in form data
        if not submitted_token:
            # We need to read the body to get form data
            # This only works if content-type is form-urlencoded
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                form_value = form.get(CSRF_FORM_FIELD)
                if isinstance(form_value, str):
                    submitted_token = form_value

        # Validate token
        if not submitted_token or not secrets.compare_digest(submitted_token, expected_token):
            return Response(content="CSRF token validation failed", status_code=403)

        response = await call_next(request)
        return response
