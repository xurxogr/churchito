"""Middleware to limit request body size."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Default limit: 1MB (sufficient for configuration JSON)
DEFAULT_MAX_BODY_SIZE = 1 * 1024 * 1024


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that limits the maximum request body size.

    Prevents denial of service attacks by sending very large bodies.
    Checks the Content-Length header before processing the request.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = DEFAULT_MAX_BODY_SIZE) -> None:
        """Initialize middleware.

        Args:
            app (ASGIApp): ASGI application
            max_body_size (int): Maximum size in bytes (default: 1MB)
        """
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request by verifying body size.

        Args:
            request (Request): Incoming request
            call_next (Callable[[Request], Awaitable[Response]]): Next handler

        Returns:
            Response: Handler response or 413 error
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
                # Invalid Content-Length, let it fail later
                pass

        response: Response = await call_next(request)
        return response
