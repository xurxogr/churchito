"""Router principal del dashboard."""

import logging
from typing import Any

import discord
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from discord_bot.common.models import Guild, GuildConfig
from discord_bot.web.dependencies import CurrentUser, DbSession, RequireAuth
from discord_bot.web.middleware import get_csrf_token

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
    bot = request.app.state.bot
    bot_name = bot.user.name if bot and bot.user else None
    return {
        "root_path": request.scope.get("root_path", ""),
        "csrf_token": get_csrf_token(request),
        "bot_name": bot_name,
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


async def _check_guild_access(
    session: Any,
    bot: Any,
    guild_id: int,
    user_id: int,
    is_bot_owner: bool,
) -> bool:
    """Check if user has access to configure a guild.

    Args:
        session: Database session
        bot: Bot instance
        guild_id: Guild ID to check
        user_id: User ID
        is_bot_owner: Whether user is bot owner

    Returns:
        bool: True if user has access
    """
    # Bot owners always have access
    if is_bot_owner:
        return True

    discord_guild = bot.get_guild(guild_id) if bot else None
    if not discord_guild:
        return False

    # Guild owners always have access
    if discord_guild.owner_id == user_id:
        return True

    # Check if user invited the bot
    result = await session.execute(select(Guild).where(Guild.id == guild_id))
    db_guild = result.scalar_one_or_none()
    if db_guild and db_guild.invited_by_id == user_id:
        return True

    # Check if user has one of the configured admin roles
    result = await session.execute(
        select(GuildConfig.value).where(
            GuildConfig.guild_id == guild_id,
            GuildConfig.cog_name == "bot",
            GuildConfig.key == "admin_roles",
        )
    )
    admin_roles_config = result.scalar_one_or_none()

    if admin_roles_config:
        admin_role_ids = set(admin_roles_config)
        # Try cache first, then fetch from API if not cached
        member = discord_guild.get_member(user_id)
        if not member:
            try:
                member = await discord_guild.fetch_member(user_id)
            except discord.HTTPException:
                member = None
        if member:
            user_role_ids = {role.id for role in member.roles}
            if user_role_ids & admin_role_ids:
                return True

    return False


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: RequireAuth,
    session: DbSession,
) -> HTMLResponse:
    """Página principal del dashboard con lista de servidores.

    Args:
        request (Request): Request de FastAPI
        user (RequireAuth): Usuario autenticado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Página del dashboard
    """
    bot = request.app.state.bot
    owner_ids = request.app.state.settings.web.owner_ids
    user_id = int(user.get("id", 0))
    is_owner = user_id in owner_ids

    logger.debug(f"Usuario ID: {user_id}, Es owner: {is_owner}")

    manageable_guilds = []

    # Check all guilds the bot is in
    # For each guild, verify user membership and access via bot (no OAuth data needed)
    if bot:
        logger.debug(f"Verificando acceso en {len(bot.guilds)} guilds del bot")
        for discord_guild in bot.guilds:
            # Bot owners see all guilds
            if is_owner:
                manageable_guilds.append(
                    {
                        "id": str(discord_guild.id),
                        "name": discord_guild.name,
                        "icon": str(discord_guild.icon.key) if discord_guild.icon else None,
                        "bot_present": True,
                        "has_access": True,
                    }
                )
                continue

            # For non-owners, check if user has access to this guild
            has_access = await _check_guild_access(
                session=session,
                bot=bot,
                guild_id=discord_guild.id,
                user_id=user_id,
                is_bot_owner=False,
            )

            if has_access:
                manageable_guilds.append(
                    {
                        "id": str(discord_guild.id),
                        "name": discord_guild.name,
                        "icon": str(discord_guild.icon.key) if discord_guild.icon else None,
                        "bot_present": True,
                        "has_access": True,
                    }
                )

    manageable_guilds.sort(key=lambda g: g["name"].lower())

    logger.debug(f"Guilds gestionables: {len(manageable_guilds)}")

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
