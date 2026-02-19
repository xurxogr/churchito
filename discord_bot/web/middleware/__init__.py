"""Middleware para la aplicación web."""

from discord_bot.web.middleware.csrf import CSRFMiddleware, get_csrf_token

__all__ = ["CSRFMiddleware", "get_csrf_token"]
