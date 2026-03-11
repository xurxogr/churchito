"""Middleware para la aplicación web."""

from discord_bot.web.middleware.content_size import ContentSizeLimitMiddleware
from discord_bot.web.middleware.csrf import CSRFMiddleware, get_csrf_token
from discord_bot.web.middleware.rate_limit import RateLimitMiddleware
from discord_bot.web.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "ContentSizeLimitMiddleware",
    "CSRFMiddleware",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "get_csrf_token",
]
