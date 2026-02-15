"""Router principal del dashboard."""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from discord_bot.web.dependencies import CurrentUser, RequireAuth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


def get_templates(request: Request) -> Jinja2Templates:
    """Obtener el motor de templates.

    Args:
        request (Request): Request de FastAPI

    Returns:
        Jinja2Templates: Motor de templates configurado
    """
    templates: Jinja2Templates = request.app.state.templates
    return templates


def base_context(request: Request) -> dict[str, Any]:
    """Contexto base para todas las plantillas.

    Args:
        request (Request): Request de FastAPI

    Returns:
        dict[str, Any]: Contexto con variables comunes
    """
    return {
        "root_path": request.scope.get("root_path", ""),
    }


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index(
    request: Request,
    user: CurrentUser,
) -> Response:
    """Página principal.

    Args:
        request (Request): Request de FastAPI
        user (CurrentUser): Usuario actual (puede ser None)

    Returns:
        Response: Página de inicio o redirección
    """
    if user:
        root_path = request.scope.get("root_path", "")
        return RedirectResponse(url=f"{root_path}/dashboard")

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={**base_context(request), "error": request.query_params.get("error")},
    )


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(
    request: Request,
    user: CurrentUser,
) -> Response:
    """Página de login.

    Args:
        request (Request): Request de FastAPI
        user (CurrentUser): Usuario actual (puede ser None)

    Returns:
        Response: Página de login o redirección
    """
    if user:
        root_path = request.scope.get("root_path", "")
        return RedirectResponse(url=f"{root_path}/dashboard")

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={**base_context(request), "error": request.query_params.get("error")},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: RequireAuth,
) -> HTMLResponse:
    """Página principal del dashboard con lista de servidores.

    Args:
        request (Request): Request de FastAPI
        user (RequireAuth): Usuario autenticado

    Returns:
        HTMLResponse: Página del dashboard
    """
    bot = request.app.state.bot
    owner_ids = request.app.state.settings.web.owner_ids
    user_id = int(user.get("id", 0))
    is_owner = user_id in owner_ids

    logger.info(f"User ID: {user_id}, Owner IDs: {owner_ids}, Is Owner: {is_owner}")

    user_guilds = user.get("guilds", [])
    logger.info(f"User has {len(user_guilds)} guilds from Discord")

    manageable_guilds = []

    for guild in user_guilds:
        permissions = int(guild.get("permissions", 0))
        is_guild_owner = guild.get("owner", False)
        # MANAGE_GUILD = 0x20, ADMINISTRATOR = 0x8
        has_manage = (permissions & 0x20) != 0 or (permissions & 0x8) != 0 or is_guild_owner

        logger.debug(
            f"Guild {guild['name']}: perms={permissions}, "
            f"manage={has_manage}, owner={is_guild_owner}"
        )

        if is_owner or has_manage:
            guild_id = int(guild.get("id", 0))
            bot_in_guild = bot and any(g.id == guild_id for g in bot.guilds)

            manageable_guilds.append(
                {
                    "id": guild["id"],
                    "name": guild["name"],
                    "icon": guild.get("icon"),
                    "bot_present": bot_in_guild,
                }
            )

    manageable_guilds.sort(key=lambda g: (not g["bot_present"], g["name"].lower()))

    logger.info(f"Manageable guilds: {len(manageable_guilds)}")

    # Bot info
    bot_info = None
    if bot and bot.user:
        bot_info = {
            "name": bot.user.name,
            "avatar": bot.user.avatar.url if bot.user.avatar else None,
            "guild_count": len(bot.guilds),
        }

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            **base_context(request),
            "user": user,
            "guilds": manageable_guilds,
            "is_owner": is_owner,
            "bot": bot_info,
        },
    )


def _get_guild_access(
    request: Request, guild_id: int, user: dict[str, Any]
) -> dict[str, Any] | None:
    """Verificar acceso al guild (versión síncrona para usar en template).

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        user (dict[str, Any]): Usuario autenticado

    Returns:
        dict[str, Any] | None: Datos del guild o None si no tiene acceso
    """
    owner_ids = request.app.state.settings.web.owner_ids
    user_id = int(user.get("id", 0))
    guilds: list[dict[str, Any]] = user.get("guilds", [])

    if user_id in owner_ids:
        for guild in guilds:
            if int(guild.get("id", 0)) == guild_id:
                return guild
        return {"id": str(guild_id), "name": f"Guild {guild_id}"}

    for guild in guilds:
        if int(guild.get("id", 0)) == guild_id:
            permissions = int(guild.get("permissions", 0))
            if permissions & 0x20:
                return guild

    return None
