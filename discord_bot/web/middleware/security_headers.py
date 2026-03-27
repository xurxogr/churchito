"""Middleware to add HTTP security headers."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Content Security Policy
# - default-src 'self': Only resources from same origin by default
# - script-src: Scripts from same origin + inline + unpkg.com (for HTMX CDN)
# - style-src: Styles from same origin + inline (required for Tailwind)
# - img-src: Images from any source (for user-provided content)
# - font-src: Fonts from same origin
# - connect-src: XHR/fetch connections to same origin
# - frame-ancestors 'none': Equivalent to X-Frame-Options: DENY
# - base-uri 'self': Restricts <base> tag
# - form-action 'self': Forms only to same origin
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src *; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# HSTS: 1 year, include subdomains
DEFAULT_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds HTTP security headers to all responses.

    Headers added:
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME sniffing
    - Referrer-Policy: Controls referrer information
    - Content-Security-Policy: Controls allowed resources
    - Strict-Transport-Security: Forces HTTPS (only if https_only=True)
    """

    def __init__(self, app: ASGIApp, https_only: bool = True) -> None:
        """Initialize middleware.

        Args:
            app (ASGIApp): ASGI application
            https_only (bool): If True, adds HSTS header
        """
        super().__init__(app)
        self.https_only = https_only

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request by adding security headers to the response.

        Args:
            request (Request): Incoming request
            call_next (Callable[[Request], Awaitable[Response]]): Next handler

        Returns:
            Response: Response with security headers added
        """
        response: Response = await call_next(request)

        # Prevent clickjacking (redundant with CSP frame-ancestors, but for older browsers)
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = DEFAULT_CSP

        # HSTS only if configured for HTTPS
        if self.https_only:
            response.headers["Strict-Transport-Security"] = DEFAULT_HSTS

        return response
