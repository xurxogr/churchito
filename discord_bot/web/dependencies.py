"""Dependencias para inyección en FastAPI."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.models import Guild as GuildModel
from discord_bot.common.models import GuildConfig

logger = logging.getLogger(__name__)


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Obtener una sesión de base de datos.

    Args:
        request (Request): Request de FastAPI

    Yields:
        AsyncSession: Sesión de base de datos
    """
    db_service = request.app.state.db_service
    async with db_service.session() as session:
        yield session


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Obtener el usuario actual de la sesión.

    Args:
        request (Request): Request de FastAPI

    Returns:
        dict[str, Any] | None: Datos del usuario o None si no está autenticado
    """
    user = request.session.get("user")
    logger.debug(f"Claves de sesión: {list(request.session.keys())}")
    logger.debug(f"Usuario en sesión: {user.get('username') if user else None}")
    return user


async def require_auth(
    user: Annotated[dict[str, Any] | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Requerir autenticación.

    Args:
        user (dict[str, Any] | None): Usuario actual de la sesión

    Returns:
        dict[str, Any]: Datos del usuario

    Raises:
        HTTPException: Si no está autenticado
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    return user


async def require_guild_access(
    request: Request,
    guild_id: int,
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Verificar que el usuario tiene acceso al guild.

    El acceso se concede si el usuario:
    - Es owner del bot (definido en config)
    - Es quien invitó al bot a este servidor
    - Es owner del servidor
    - Tiene uno de los roles de admin configurados para el bot

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        user (dict[str, Any]): Usuario autenticado

    Returns:
        dict[str, Any]: Datos del usuario

    Raises:
        HTTPException: Si no tiene acceso
    """
    user_id = int(user.get("id", 0))

    # 1. Check if user is bot owner (from config)
    owner_ids = request.app.state.settings.web.owner_ids
    if user_id in owner_ids:
        return user

    # Find the user's guild data from OAuth
    user_guild = None
    for g in user.get("guilds", []):
        if int(g.get("id", 0)) == guild_id:
            user_guild = g
            break

    if not user_guild:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres miembro de este servidor",
        )

    # Get database info
    db_service = request.app.state.db_service
    async with db_service.session() as session:
        # Get guild from database
        result = await session.execute(select(GuildModel).where(GuildModel.id == guild_id))
        db_guild = result.scalar_one_or_none()

        # 2. Check if user is the one who invited the bot
        if db_guild and db_guild.invited_by_id == user_id:
            return user

        # 3. Check if user is guild owner
        # Discord sends owner info in the guild object from OAuth
        # The "owner" field is True if the user owns the guild
        if user_guild.get("owner"):
            return user

        # 4. Check if user has one of the configured admin roles
        # Get admin_roles config for this guild
        result = await session.execute(
            select(GuildConfig.value).where(
                GuildConfig.guild_id == guild_id,
                GuildConfig.cog_name == "bot",
                GuildConfig.key == "admin_roles",
            )
        )
        admin_roles_config = result.scalar_one_or_none()

        if admin_roles_config:
            admin_role_ids = set(admin_roles_config)  # List of role IDs

            # Get user's roles in this guild from the bot
            bot = request.app.state.bot
            if bot:
                discord_guild = bot.get_guild(guild_id)
                if discord_guild:
                    member = discord_guild.get_member(user_id)
                    if member:
                        user_role_ids = {role.id for role in member.roles}
                        if user_role_ids & admin_role_ids:
                            return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para gestionar este servidor",
    )


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[dict[str, Any] | None, Depends(get_current_user)]
RequireAuth = Annotated[dict[str, Any], Depends(require_auth)]
