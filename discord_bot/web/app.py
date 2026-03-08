"""Factory para crear la aplicación FastAPI del dashboard."""

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
from discord_bot.web.auth.oauth import router as auth_router
from discord_bot.web.dependencies import NotAuthenticatedException
from discord_bot.web.middleware import CSRFMiddleware, RateLimitMiddleware
from discord_bot.web.routers.config import router as config_router
from discord_bot.web.routers.dashboard import router as dashboard_router

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent


def create_app(
    settings: AppSettings,
    db_service: DatabaseService,
    bot: object | None = None,
) -> FastAPI:
    """Crear la aplicación FastAPI del dashboard.

    Args:
        settings (AppSettings): Configuración de la aplicación
        db_service (DatabaseService): Servicio de base de datos
        bot (object | None): Instancia del bot de Discord (opcional)

    Returns:
        FastAPI: Aplicación configurada
    """
    app = FastAPI(
        title="Bot Dashboard",
        description="Dashboard web para configuración del bot de Discord",
        version="1.0.0",
        root_path=settings.web.root_path,
    )

    secret_key = settings.web.secret_key
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        logger.warning(
            "No se configuró WEB__SECRET_KEY, usando clave generada automáticamente. "
            "Las sesiones no persistirán entre reinicios."
        )

    # Middleware se procesa en orden inverso al que se añade
    # (el último añadido procesa primero)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="bot_session",
        max_age=settings.web.session_max_age,
        same_site="lax",
        https_only=settings.web.https_only,
    )
    # ProxyHeadersMiddleware lee X-Forwarded-Proto y X-Forwarded-For
    # para que FastAPI sepa el protocolo/IP real cuando está detrás de un proxy
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

    app.state.settings = settings
    app.state.db_service = db_service
    app.state.bot = bot

    templates_dir = WEB_DIR / "templates"
    static_dir = WEB_DIR / "static"

    app.state.templates = Jinja2Templates(directory=str(templates_dir))

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
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "root_path": root_path,
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
            status_code=exc.status_code,
        )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Endpoint de verificación de salud para Docker healthcheck."""
        return {"status": "ok"}

    logger.info("Dashboard web inicializado")
    return app


async def run_web_server(
    settings: AppSettings,
    db_service: DatabaseService,
    bot: object | None = None,
) -> None:
    """Ejecutar el servidor web.

    Args:
        settings (AppSettings): Configuración de la aplicación
        db_service (DatabaseService): Servicio de base de datos
        bot (object | None): Instancia del bot de Discord (opcional)
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
