"""Dependencias para inyección en FastAPI."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

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
    logger.debug(f"Session keys: {list(request.session.keys())}")
    logger.debug(f"User from session: {user.get('username') if user else None}")
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

    El usuario debe tener permiso MANAGE_GUILD o ser owner del bot.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        user (dict[str, Any]): Usuario autenticado

    Returns:
        dict[str, Any]: Datos del usuario

    Raises:
        HTTPException: Si no tiene acceso
    """
    owner_ids = request.app.state.settings.web.owner_ids
    user_id = int(user.get("id", 0))

    if user_id in owner_ids:
        return user

    user_guilds = user.get("guilds", [])
    for guild in user_guilds:
        if int(guild.get("id", 0)) == guild_id:
            permissions = int(guild.get("permissions", 0))
            if permissions & 0x20:
                return user
            break

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para gestionar este servidor",
    )


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[dict[str, Any] | None, Depends(get_current_user)]
RequireAuth = Annotated[dict[str, Any], Depends(require_auth)]
