"""Middleware to limit request body size."""

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Default limit: 1MB (sufficient for configuration JSON)
DEFAULT_MAX_BODY_SIZE = 1 * 1024 * 1024


class RequestBodyTooLargeError(Exception):
    """Raised when the streamed request body exceeds the configured limit."""


class ContentSizeLimitMiddleware:
    """Middleware that limits the maximum request body size.

    Prevents denial of service attacks by sending very large bodies.
    Rejects early based on the Content-Length header when present, and also
    counts the bytes actually received so chunked transfer-encoding (which
    carries no Content-Length) cannot bypass the limit.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = DEFAULT_MAX_BODY_SIZE) -> None:
        """Initialize middleware.

        Args:
            app (ASGIApp): ASGI application
            max_body_size (int): Maximum size in bytes (default: 1MB)
        """
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request by verifying body size.

        Args:
            scope (Scope): ASGI connection scope
            receive (Receive): ASGI receive channel
            send (Send): ASGI send channel
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._declared_length_exceeds_limit(scope=scope):
            await self._send_too_large(scope=scope, receive=receive, send=send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_size:
                    raise RequestBodyTooLargeError()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLargeError:
            if response_started:
                raise
            await self._send_too_large(scope=scope, receive=receive, send=send)

    def _declared_length_exceeds_limit(self, scope: Scope) -> bool:
        """Check whether the Content-Length header declares an oversized body.

        Args:
            scope (Scope): ASGI connection scope

        Returns:
            bool: True if Content-Length is a valid integer above the limit
        """
        content_length = Headers(scope=scope).get("content-length")
        if not content_length:
            return False
        try:
            return int(content_length) > self.max_body_size
        except ValueError:
            # Invalid Content-Length, let it fail later
            return False

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send a 413 response.

        Args:
            scope (Scope): ASGI connection scope
            receive (Receive): ASGI receive channel
            send (Send): ASGI send channel
        """
        response = Response(
            content="Request body too large",
            status_code=413,
            headers={"Content-Type": "text/plain"},
        )
        await response(scope, receive, send)
