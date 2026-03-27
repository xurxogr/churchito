"""Dependencies for FastAPI dependency injection."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import discord
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.models import Guild as GuildModel
from discord_bot.common.models import GuildConfig

logger = logging.getLogger(__name__)


class NotAuthenticatedException(Exception):
    """Exception to indicate the user is not authenticated.

    Used instead of HTTPException to allow redirection to login
    instead of showing a 401 error page.
    """

    pass


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get a database session.

    Args:
        request (Request): FastAPI request

    Yields:
        AsyncSession: Database session
    """
    db_service = request.app.state.db_service
    async with db_service.session() as session:
        yield session


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Get the current user from the session.

    Args:
        request (Request): FastAPI request

    Returns:
        dict[str, Any] | None: User data or None if not authenticated
    """
    user = request.session.get("user")
    logger.debug(f"Session keys: {list(request.session.keys())}")
    logger.debug(f"User in session: {user.get('username') if user else None}")
    return user


async def require_auth(
    user: Annotated[dict[str, Any] | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Require authentication.

    Args:
        user (dict[str, Any] | None): Current user from session

    Returns:
        dict[str, Any]: User data

    Raises:
        NotAuthenticatedException: If not authenticated (results in redirect to login)
    """
    if user is None:
        raise NotAuthenticatedException()
    return user


async def require_guild_access(
    request: Request,
    guild_id: int,
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Verify that the user has access to the guild.

    Access is granted if the user:
    - Is the bot owner (defined in config)
    - Is the one who invited the bot to this server
    - Is the server owner
    - Has one of the admin roles configured for the bot

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        user (dict[str, Any]): Authenticated user

    Returns:
        dict[str, Any]: User data

    Raises:
        HTTPException: If access is denied
    """
    user_id = int(user.get("id", 0))

    # 1. Check if user is bot owner (from config)
    owner_ids = request.app.state.settings.web.owner_ids
    if user_id in owner_ids:
        return user

    # 2. Check if bot is in the guild
    bot = request.app.state.bot
    discord_guild = bot.get_guild(guild_id) if bot else None
    if not discord_guild:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to manage this server",
        )

    # 3. Check if user is guild owner
    if discord_guild.owner_id == user_id:
        return user

    # Get database info
    db_service = request.app.state.db_service
    async with db_service.session() as session:
        # 4. Check if user is the one who invited the bot
        result = await session.execute(select(GuildModel).where(GuildModel.id == guild_id))
        db_guild = result.scalar_one_or_none()
        if db_guild and db_guild.invited_by_id == user_id:
            return user

        # 5. Check if user has one of the configured admin roles
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
                    return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to manage this server",
    )


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[dict[str, Any] | None, Depends(get_current_user)]
RequireAuth = Annotated[dict[str, Any], Depends(require_auth)]
