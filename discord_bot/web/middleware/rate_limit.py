"""Rate limiting middleware for abuse protection.

IMPORTANT: This rate limiter uses local in-memory storage.
It does NOT scale in multi-worker deployments (each worker has its own state).

For production with multiple workers, it is recommended to:
1. Disable this middleware (WEB__RATE_LIMIT_ENABLED=false)
2. Use external rate limiting: nginx, HAProxy, Cloudflare, etc.
"""

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Rate limits configuration by route
RATE_LIMITS: dict[str, tuple[int, int]] = {
    # (requests, window_seconds)
    "/auth/login": (10, 60),  # 10 requests per minute
    "/auth/callback": (10, 60),  # 10 requests per minute
}

# Default limit for POST configuration routes
DEFAULT_POST_LIMIT = (30, 60)  # 30 requests per minute


@dataclass
class RateLimitState:
    """Rate limiting state for an IP/route."""

    requests: list[float] = field(default_factory=list)

    def clean_old_requests(self, window_seconds: int) -> None:
        """Remove requests outside the time window."""
        cutoff = time.time() - window_seconds
        self.requests = [t for t in self.requests if t > cutoff]

    def is_limited(self, max_requests: int, window_seconds: int) -> bool:
        """Check if the limit has been exceeded."""
        self.clean_old_requests(window_seconds)
        return len(self.requests) >= max_requests

    def add_request(self) -> None:
        """Record a new request."""
        self.requests.append(time.time())


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request rate.

    Implements a simple sliding window algorithm.
    Limits are applied per IP + route.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.

        Args:
            app (ASGIApp): ASGI application
        """
        super().__init__(app)
        # State per (ip, path_pattern)
        self._state: dict[tuple[str, str], RateLimitState] = defaultdict(RateLimitState)
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP considering proxies."""
        # X-Forwarded-For may contain multiple IPs
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()

        # X-Real-IP is another common option
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to direct client
        if request.client:
            return request.client.host

        return "unknown"

    def _get_path_pattern(self, path: str) -> str:
        """Get route pattern for rate limiting.

        Normalizes routes with variable IDs.
        """
        # For config routes, group by pattern
        parts = path.split("/")
        if len(parts) >= 4 and parts[1] == "guild":
            # /guild/{id}/cog/{name}/... -> /guild/*/cog/*/*
            if len(parts) >= 5 and parts[3] == "cog":
                return (
                    "/guild/*/cog/*/" + "/".join(parts[5:]) if len(parts) > 5 else "/guild/*/cog/*"
                )
        return path

    def _get_limit(self, path: str, method: str) -> tuple[int, int] | None:
        """Get limit for a route.

        Returns:
            Tuple (max_requests, window_seconds) or None if no limit.
        """
        # Check specific limits
        if path in RATE_LIMITS:
            return RATE_LIMITS[path]

        # Apply default limit to POSTs on /guild/
        if method == "POST" and path.startswith("/guild/"):
            return DEFAULT_POST_LIMIT

        return None

    def _periodic_cleanup(self) -> None:
        """Clean old states periodically."""
        now = time.time()
        # Clean every 5 minutes
        if now - self._last_cleanup < 300:
            return

        self._last_cleanup = now
        # Remove states without recent requests (more than 10 minutes)
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
        """Process request applying rate limiting."""
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
