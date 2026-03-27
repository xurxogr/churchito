"""Factory to create the FastAPI dashboard application."""

import logging
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from discord_bot.common.core.app_settings import AppSettings
from discord_bot.common.services.database import DatabaseService
from discord_bot.i18n import get_i18n_service
from discord_bot.web.auth.oauth import router as auth_router
from discord_bot.web.dependencies import NotAuthenticatedException
from discord_bot.web.middleware import (
    ContentSizeLimitMiddleware,
    CSRFMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from discord_bot.web.routers.config import router as config_router
from discord_bot.web.routers.dashboard import router as dashboard_router

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent


def create_app(
    settings: AppSettings,
    db_service: DatabaseService,
    bot: object | None = None,
) -> FastAPI:
    """Create the FastAPI dashboard application.

    Args:
        settings (AppSettings): Application settings
        db_service (DatabaseService): Database service
        bot (object | None): Discord bot instance (optional)

    Returns:
        FastAPI: Configured application
    """
    app = FastAPI(
        title="Bot Dashboard",
        description="Web dashboard for Discord bot configuration",
        version="1.0.0",
        root_path=settings.web.root_path,
    )

    secret_key = settings.web.secret_key
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        logger.warning(
            "WEB__SECRET_KEY not configured, using auto-generated key. "
            "Sessions will not persist between restarts."
        )

    # Middleware is processed in reverse order of addition
    # (the last added processes first)
    # SecurityHeadersMiddleware is added first so it processes last (adds headers to response)
    app.add_middleware(
        SecurityHeadersMiddleware,
        https_only=settings.web.https_only,
    )
    if settings.web.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)
        logger.warning(
            "Internal rate limiting enabled. NOTE: Uses local memory and does NOT scale "
            "in multi-worker deployments. For production with multiple workers, "
            "set WEB__RATE_LIMIT_ENABLED=false and use external rate limiting."
        )
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="bot_session",
        max_age=settings.web.session_max_age,
        same_site="lax",
        https_only=settings.web.https_only,
    )
    # ProxyHeadersMiddleware reads X-Forwarded-Proto and X-Forwarded-For
    # so FastAPI knows the real protocol/IP when behind a proxy
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=settings.web.trusted_hosts or ["127.0.0.1"],
    )
    # ContentSizeLimitMiddleware is added last to process first
    # and reject large bodies before other processing
    app.add_middleware(ContentSizeLimitMiddleware)

    app.state.settings = settings
    app.state.db_service = db_service
    app.state.bot = bot

    templates_dir = WEB_DIR / "templates"
    static_dir = WEB_DIR / "static"

    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Register i18n globals for templates
    i18n = get_i18n_service()
    app.state.templates.env.globals["_"] = i18n.translate
    app.state.templates.env.globals["LANGUAGES"] = i18n.SUPPORTED_LANGUAGES
    app.state.i18n = i18n

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(config_router)

    @app.exception_handler(NotAuthenticatedException)
    async def not_authenticated_handler(
        request: Request, exc: NotAuthenticatedException
    ) -> RedirectResponse:
        """Handle not authenticated by redirecting to login."""
        root_path = request.scope.get("root_path", "")
        return RedirectResponse(url=f"{root_path}/login", status_code=303)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> HTMLResponse:
        """Handle HTTP exceptions with HTML error page."""
        templates: Jinja2Templates = app.state.templates
        root_path = request.scope.get("root_path", "")

        # For 5xx errors, don't expose internal details
        if exc.status_code >= 500:
            logger.error(f"Error {exc.status_code}: {exc.detail}")
            detail = "Internal server error"
        else:
            detail = exc.detail

        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "root_path": root_path,
                "status_code": exc.status_code,
                "detail": detail,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        """Handle unexpected exceptions with generic error page."""
        templates: Jinja2Templates = app.state.templates
        root_path = request.scope.get("root_path", "")

        # Log the real error but don't expose it to the user
        logger.exception("Unhandled error")

        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "root_path": root_path,
                "status_code": 500,
                "detail": "Internal server error",
            },
            status_code=500,
        )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint for Docker healthcheck."""
        return {"status": "ok"}

    logger.info("Web dashboard initialized")
    return app


async def run_web_server(
    settings: AppSettings,
    db_service: DatabaseService,
    bot: object | None = None,
) -> None:
    """Run the web server.

    Args:
        settings (AppSettings): Application settings
        db_service (DatabaseService): Database service
        bot (object | None): Discord bot instance (optional)
    """
    app = create_app(settings, db_service, bot)

    config = uvicorn.Config(
        app,
        host=settings.web.host,
        port=settings.web.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
