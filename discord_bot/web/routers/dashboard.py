"""Main dashboard router."""

import logging
from typing import Any

import discord
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from discord_bot.common.models import Guild, GuildConfig
from discord_bot.i18n import get_i18n_service
from discord_bot.web.dependencies import CurrentUser, DbSession, RequireAuth
from discord_bot.web.middleware import get_csrf_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


def get_templates(request: Request) -> Jinja2Templates:
    """Get the template engine.

    Args:
        request (Request): FastAPI request

    Returns:
        Jinja2Templates: Configured template engine
    """
    templates: Jinja2Templates = request.app.state.templates
    return templates


def get_browser_language(request: Request) -> str:
    """Get the language from the browser's Accept-Language header.

    Args:
        request: FastAPI request

    Returns:
        str: Language code ('en' or 'es', defaults to 'en')
    """
    i18n = get_i18n_service()
    accept_language = request.headers.get("Accept-Language", "")

    # Parse Accept-Language header (e.g., "es-ES,es;q=0.9,en;q=0.8")
    for part in accept_language.split(","):
        # Extract language code (before any ';' for quality factor)
        lang_part = part.split(";")[0].strip()
        # Get base language (e.g., "es" from "es-ES")
        base_lang = lang_part.split("-")[0].lower()

        if base_lang in i18n.SUPPORTED_LANGUAGES:
            return base_lang

    return i18n.DEFAULT_LANGUAGE


def base_context(request: Request, lang: str | None = None) -> dict[str, Any]:
    """Base context for all templates.

    Args:
        request (Request): FastAPI request
        lang (str | None): Language code (uses browser language if not provided)

    Returns:
        dict[str, Any]: Context with common variables
    """
    bot = request.app.state.bot
    bot_name = bot.user.name if bot and bot.user else None
    return {
        "root_path": request.scope.get("root_path", ""),
        "csrf_token": get_csrf_token(request),
        "bot_name": bot_name,
        "lang": lang or get_browser_language(request),
    }


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index(
    request: Request,
    user: CurrentUser,
) -> Response:
    """Main page.

    Args:
        request (Request): FastAPI request
        user (CurrentUser): Current user (may be None)

    Returns:
        Response: Home page or redirect
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
    """Login page.

    Args:
        request (Request): FastAPI request
        user (CurrentUser): Current user (may be None)

    Returns:
        Response: Login page or redirect
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


class GuildAccessData(BaseModel):
    """Database-backed access data for the guilds shown on the dashboard."""

    model_config = ConfigDict(extra="forbid")

    invited_guild_ids: set[int]
    admin_role_ids: dict[int, set[int]]


async def _load_guild_access_data(
    session: Any,
    user_id: int,
    guild_ids: list[int],
) -> GuildAccessData:
    """Load, in two queries, the data needed to check access to many guilds.

    Args:
        session (Any): Database session.
        user_id (int): User whose access is being checked.
        guild_ids (list[int]): Guilds the bot is currently in.

    Returns:
        GuildAccessData: Guilds the user invited the bot to and the configured
            admin roles per guild.
    """
    if not guild_ids:
        return GuildAccessData(invited_guild_ids=set(), admin_role_ids={})

    result = await session.execute(
        select(Guild.id).where(Guild.id.in_(guild_ids), Guild.invited_by_id == user_id)
    )
    invited_guild_ids = set(result.scalars().all())

    result = await session.execute(
        select(GuildConfig.guild_id, GuildConfig.value).where(
            GuildConfig.guild_id.in_(guild_ids),
            GuildConfig.cog_name == "bot",
            GuildConfig.key == "admin_roles",
        )
    )
    admin_role_ids = {
        guild_id: {int(role_id) for role_id in value} for guild_id, value in result.all() if value
    }
    return GuildAccessData(invited_guild_ids=invited_guild_ids, admin_role_ids=admin_role_ids)


async def _check_guild_access(
    access_data: GuildAccessData,
    bot: Any,
    guild_id: int,
    user_id: int,
    is_bot_owner: bool,
) -> bool:
    """Check if user has access to configure a guild.

    Args:
        access_data (GuildAccessData): Preloaded database data, shared by every
            guild checked in the same request (see _load_guild_access_data).
        bot (Any): Bot instance.
        guild_id (int): Guild ID to check.
        user_id (int): User ID.
        is_bot_owner (bool): Whether user is bot owner.

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

    # Users who invited the bot have access
    if guild_id in access_data.invited_guild_ids:
        return True

    # Check if user has one of the configured admin roles
    admin_role_ids = access_data.admin_role_ids.get(guild_id)
    if admin_role_ids:
        # The member cache is authoritative once the guild has been chunked
        # (members intent); only fall back to the API while it is incomplete
        member = discord_guild.get_member(user_id)
        if member is None and not discord_guild.chunked:
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
    """Main dashboard page with server list.

    Args:
        request (Request): FastAPI request
        user (RequireAuth): Authenticated user
        session (DbSession): Database session

    Returns:
        HTMLResponse: Dashboard page
    """
    bot = request.app.state.bot
    owner_ids = request.app.state.settings.web.owner_ids
    user_id = int(user.get("id", 0))
    is_owner = user_id in owner_ids

    logger.debug(f"User ID: {user_id}, Is owner: {is_owner}")

    manageable_guilds = []

    # Check all guilds the bot is in
    # For each guild, verify user membership and access via bot (no OAuth data needed)
    if bot:
        logger.debug(f"Checking access in {len(bot.guilds)} bot guilds")
        access_data = GuildAccessData(invited_guild_ids=set(), admin_role_ids={})
        if not is_owner:
            # One batched load instead of two queries per guild
            access_data = await _load_guild_access_data(
                session=session,
                user_id=user_id,
                guild_ids=[discord_guild.id for discord_guild in bot.guilds],
            )
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
                access_data=access_data,
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

    logger.debug(f"Manageable guilds: {len(manageable_guilds)}")

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
