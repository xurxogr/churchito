"""Router for server configuration."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, NamedTuple

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.embed_builder import COLOR_TAGS, GLOBAL_PLACEHOLDERS
from discord_bot.common.utils.keyed_locks import KeyedLocks
from discord_bot.i18n import get_i18n_service
from discord_bot.web.dependencies import (
    DbSession,
    RequireAuth,
    is_bot_owner,
    require_bot_owner,
    require_guild_access,
)
from discord_bot.web.middleware import get_csrf_token
from discord_bot.web.views.cog_settings import (
    build_option_data,
    build_preview_data,
    get_locked_options,
    list_assignable_roles,
    list_selectable_roles,
    list_sendable_channels,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guild", tags=["config"])

# Serialize toggles per (guild, cog): a double click would otherwise read the
# same state twice and apply the same flip (and its cog callback) two times
cog_toggle_locks = KeyedLocks()


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
        lang (str | None): Language code (uses default if not provided)

    Returns:
        dict[str, Any]: Context with common variables
    """
    bot = request.app.state.bot
    bot_name = bot.user.name if bot and bot.user else None
    i18n = get_i18n_service()
    return {
        "root_path": request.scope.get("root_path", ""),
        "csrf_token": get_csrf_token(request),
        "bot_name": bot_name,
        "lang": lang or i18n.DEFAULT_LANGUAGE,
    }


async def guild_access_dep(
    request: Request,
    guild_id: Annotated[int, Path()],
    user: RequireAuth,
) -> dict[str, Any]:
    """Dependency to verify guild access.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        user (RequireAuth): Authenticated user

    Returns:
        dict[str, Any]: User data if they have access
    """
    return await require_guild_access(request, guild_id, user)


GuildAccess = Annotated[dict[str, Any], Depends(guild_access_dep)]


def _get_guild_info(bot: Any, guild_id: int) -> dict[str, Any]:
    """Get guild information from the bot.

    Args:
        bot: Bot instance
        guild_id (int): Guild ID

    Returns:
        dict[str, Any]: Guild information
    """
    if bot:
        discord_guild = bot.get_guild(guild_id)
        if discord_guild:
            return {
                "id": str(discord_guild.id),
                "name": discord_guild.name,
                "icon": str(discord_guild.icon.key) if discord_guild.icon else None,
            }
    return {"id": str(guild_id), "name": f"Server {guild_id}"}


@router.get("/{guild_id}", response_class=HTMLResponse)
async def guild_config(
    request: Request,
    guild_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Server configuration page.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Configuration page
    """
    # Verify bot is in this guild
    bot = request.app.state.bot
    if not bot or not bot.get_guild(guild_id):
        raise HTTPException(
            status_code=404,
            detail="You don't have permission to manage this server",
        )

    # Get language from browser
    lang = get_browser_language(request)
    i18n = get_i18n_service()

    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    schemas = schema_service.get_all_schemas()
    enabled_cogs = await config_service.get_enabled_cogs(guild_id)

    cogs_data = []
    # Sort cogs: "bot" first, then alphabetically by display_name

    def cog_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        cog_name, schema = item
        # "bot" gets priority 0, everything else gets 1
        priority = 0 if cog_name == "bot" else 1
        # Get translated display name for sorting
        translated_name = i18n.translate(f"cogs.{cog_name}.display_name", lang)
        if translated_name == f"cogs.{cog_name}.display_name":
            translated_name = schema.display_name
        return (priority, translated_name)

    for cog_name, schema in sorted(schemas.items(), key=cog_sort_key):
        is_enabled = enabled_cogs.get(cog_name, False)
        # Get translated display name and description
        translated_display_name = i18n.translate(f"cogs.{cog_name}.display_name", lang)
        translated_description = i18n.translate(f"cogs.{cog_name}.description", lang)
        # Fallback to original if translation is the key itself
        if translated_display_name == f"cogs.{cog_name}.display_name":
            translated_display_name = schema.display_name
        if translated_description == f"cogs.{cog_name}.description":
            translated_description = schema.description

        cogs_data.append(
            {
                "name": cog_name,
                "display_name": translated_display_name,
                "description": translated_description,
                "icon": schema.icon or "⚙️",
                "enabled": is_enabled,
                "toggleable": schema.toggleable,
                "options_count": len(schema.options),
            }
        )

    guild_info = _get_guild_info(request.app.state.bot, guild_id)
    templates = get_templates(request)

    return templates.TemplateResponse(
        request=request,
        name="guild_config.html",
        context={
            **base_context(request, lang),
            "user": user,
            "guild": guild_info,
            "guild_id": guild_id,
            "cogs": cogs_data,
        },
    )


class GuildContext(NamedTuple):
    """Discord guild plus the dropdown sources and locked options for the settings page."""

    guild: Any
    channels: list[dict[str, Any]]
    roles: list[dict[str, Any]]
    assignable_roles: list[dict[str, Any]]
    locked_options: dict[str, dict[str, Any]]


def _guild_context(bot: Any, guild_id: int, cog_name: str) -> GuildContext:
    """Resolve the Discord guild plus the dropdown sources and locked options.

    ``roles`` lists every role (for pickers that only check membership) while
    ``assignable_roles`` keeps only those below the bot's top role (for pickers
    whose roles the bot assigns or removes).

    Args:
        bot (Any): Bot instance (may be None when running without the bot)
        guild_id (int): Guild ID
        cog_name (str): Cog name

    Returns:
        GuildContext: Guild (or None), sendable channels, all roles, assignable roles and
            locked options
    """
    if not bot:
        return GuildContext(
            guild=None, channels=[], roles=[], assignable_roles=[], locked_options={}
        )
    discord_guild = bot.get_guild(guild_id)
    channels: list[dict[str, Any]] = []
    roles: list[dict[str, Any]] = []
    assignable_roles: list[dict[str, Any]] = []
    if discord_guild:
        bot_member = discord_guild.get_member(bot.user.id)
        channels = list_sendable_channels(guild=discord_guild, bot_member=bot_member)
        roles = list_selectable_roles(guild=discord_guild)
        assignable_roles = list_assignable_roles(guild=discord_guild)
    return GuildContext(
        guild=discord_guild,
        channels=channels,
        roles=roles,
        assignable_roles=assignable_roles,
        locked_options=get_locked_options(bot=bot, cog_name=cog_name),
    )


def _resolve_member(discord_guild: Any, user: dict[str, Any] | None) -> Any:
    """Look up the dashboard user's guild member for the placeholder preview.

    Args:
        discord_guild (Any): Discord guild (or None)
        user (dict[str, Any] | None): Authenticated user

    Returns:
        Any: Guild member, or None when unavailable
    """
    if not discord_guild or not user:
        return None
    user_id = user.get("id")
    return discord_guild.get_member(int(user_id)) if user_id else None


async def _render_cog_settings(
    request: Request,
    guild_id: int,
    cog_name: str,
    session: Any,
    user: dict[str, Any] | None = None,
    error: str | None = None,
    lang: str | None = None,
) -> HTMLResponse:
    """Render the cog configuration partial.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        session (Any): Database session
        user (dict[str, Any] | None): Authenticated user (for placeholder preview)
        error (str | None): Optional error message
        lang (str | None): Language code

    Returns:
        HTMLResponse: Partial HTML with cog configuration

    Raises:
        HTTPException: 404 when the cog has no configuration schema
    """
    if lang is None:
        lang = get_browser_language(request)

    schema = get_config_schema_service().get_schema(cog_name)
    if not schema:
        raise HTTPException(status_code=404, detail="Cog not found")

    config_service = ConfigService(session)
    config_values = await config_service.get_all_config(guild_id, cog_name)
    is_enabled = await config_service.is_cog_enabled(guild_id, cog_name)

    discord_guild, channels, roles, assignable_roles, locked_options = _guild_context(
        bot=request.app.state.bot, guild_id=guild_id, cog_name=cog_name
    )
    cog_translations = get_i18n_service().get_cog_translations(cog_name, lang)

    # Locked options don't appear in the UI
    options_data = [
        build_option_data(
            option=opt,
            config_values=config_values,
            guild=discord_guild,
            cog_translations=cog_translations,
        )
        for opt in schema.options
        if opt.key not in locked_options
    ]

    guild_name = discord_guild.name if discord_guild else f"Server {guild_id}"
    preview_data = build_preview_data(
        guild_id=guild_id,
        guild_name=guild_name,
        member_count=discord_guild.member_count if discord_guild else 0,
        user=user,
        member=_resolve_member(discord_guild=discord_guild, user=user),
        now=datetime.now(UTC),
    )

    return get_templates(request).TemplateResponse(
        request=request,
        name="partials/cog_settings.html",
        context={
            **base_context(request, lang),
            "guild_id": guild_id,
            "guild_name": guild_name,
            "cog_name": cog_name,
            "schema": {
                "display_name": cog_translations.get("display_name", schema.display_name),
                "description": cog_translations.get("description", schema.description),
                "icon": schema.icon or "⚙️",
                "toggleable": schema.toggleable,
            },
            "options": options_data,
            "enabled": is_enabled,
            "can_reload": is_bot_owner(request=request, user=user) if user else False,
            "channels": channels,
            "roles": roles,
            "assignable_roles": assignable_roles,
            "ConfigOptionType": ConfigOptionType,
            "error": error,
            "global_placeholders": GLOBAL_PLACEHOLDERS,
            "color_tags": COLOR_TAGS,
            "preview_data": preview_data,
        },
    )


@router.get("/{guild_id}/cog/{cog_name}", response_class=HTMLResponse)
async def cog_settings(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Get the cog configuration partial (HTMX).

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Partial HTML with cog configuration
    """
    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
    )


@router.post("/{guild_id}/cog/{cog_name}/toggle", response_class=HTMLResponse)
async def toggle_cog(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Toggle cog enabled state.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Updated partial
    """
    # Validate cog exists before any DB operation
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(cog_name):
        raise HTTPException(status_code=404, detail="Cog not found")

    config_service = ConfigService(session)
    async with cog_toggle_locks.acquire((guild_id, cog_name)):
        current = await config_service.is_cog_enabled(guild_id, cog_name)
        new_state = not current
        await config_service.set_cog_enabled(guild_id, cog_name, new_state)

        # Commit so the cog sees the change in its own session
        await session.commit()

        # Notify the cog of the change; report it if the bot could not apply it
        apply_error = await _notify_cog_toggled(
            request=request, guild_id=guild_id, cog_name=cog_name, enabled=new_state
        )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
        error=apply_error,
    )


@router.post("/{guild_id}/cog/{cog_name}/option/{key}", response_class=HTMLResponse)
async def update_option(
    request: Request,
    guild_id: int,
    cog_name: str,
    key: str,
    user: GuildAccess,
    session: DbSession,
    value: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Update a configuration option.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        key (str): Option key
        value (str): New value (as form string)
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Updated partial
    """
    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    option = schema_service.get_option(cog_name, key)
    if not option:
        raise HTTPException(status_code=404, detail="Option not found")

    locked_options = get_locked_options(bot=request.app.state.bot, cog_name=cog_name)
    converted_value, guild_error = _prepare_option_value(
        request=request,
        guild_id=guild_id,
        option=option,
        value=value,
        locked_options=locked_options,
    )
    if guild_error:
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error=guild_error,
        )

    success, validation_error = await config_service.set_value(
        guild_id=guild_id, cog_name=cog_name, key=key, value=converted_value
    )

    if not success:
        logger.warning(f"Error saving configuration: {validation_error}")
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error=validation_error,
        )

    # Commit so the cog sees the changes in its own session
    await session.commit()

    # Notify the cog that a configuration changed; report it if it could not apply it
    apply_error = await _notify_cog_config_changed(
        request=request, guild_id=guild_id, cog_name=cog_name, keys=[key]
    )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
        error=apply_error,
    )


@router.post("/{guild_id}/cog/{cog_name}/options", response_class=HTMLResponse)
async def update_options_batch(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Update multiple configuration options in batch.

    Saves all options to DB first, then notifies the cog once.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Updated partial
    """
    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    # Validate Content-Type to prevent CSRF attacks
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/json",
        )

    # Parse JSON body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    options_to_save = body.get("options", {}) if isinstance(body, dict) else None
    if not isinstance(options_to_save, dict):
        raise HTTPException(status_code=400, detail="'options' must be an object")

    if not options_to_save:
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
        )

    saved_keys: list[str] = []
    errors: list[str] = []
    values_to_save: dict[str, Any] = {}
    locked_options = get_locked_options(bot=request.app.state.bot, cog_name=cog_name)

    # Convert and check every option first, then save them in one go
    for key, value in options_to_save.items():
        option = schema_service.get_option(cog_name, key)
        if not option:
            errors.append(f"Option '{key}' not found")
            continue

        converted_value, guild_error = _prepare_option_value(
            request=request,
            guild_id=guild_id,
            option=option,
            value=value,
            locked_options=locked_options,
        )
        if guild_error:
            errors.append(guild_error)
            continue

        values_to_save[key] = converted_value

    if values_to_save:
        saved_keys, validation_errors = await config_service.set_values(
            guild_id=guild_id, cog_name=cog_name, values=values_to_save
        )
        errors.extend(f"{key}: {message}" for key, message in validation_errors.items())

    # Commit all changes at once
    await session.commit()

    # Notify cog once with all changed keys; report it if it could not apply them
    if saved_keys:
        apply_error = await _notify_cog_config_changed(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            keys=saved_keys,
        )
        if apply_error:
            errors.append(apply_error)

    error_message = "; ".join(errors) if errors else None
    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
        error=error_message,
    )


@router.post("/{guild_id}/cog/{cog_name}/reload", response_class=HTMLResponse)
async def reload_cog(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Reload a cog (extension reload).

    Reloading an extension affects every guild served by this bot process,
    so it is restricted to bot owners even though the route is guild-scoped.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Updated partial

    Raises:
        HTTPException: 403 if the user is not a bot owner, 404 if the cog does not exist
    """
    require_bot_owner(request=request, user=user)

    # Validate cog exists before any operation
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(cog_name):
        raise HTTPException(status_code=404, detail="Cog not found")

    # The "bot" cog cannot be reloaded
    if cog_name == "bot":
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error="The 'bot' module cannot be reloaded",
        )

    bot = request.app.state.bot
    if not bot:
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error="Bot not available",
        )

    extension_name = f"discord_bot.{cog_name}.cog"
    try:
        await bot.reload_extension(extension_name)
        logger.info(f"Cog {cog_name} reloaded by user {user.get('id')}")
    except Exception as e:
        logger.error(f"Error reloading cog {cog_name}: {e}")
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error=f"Error reloading: {e}",
        )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
    )


def _cog_apply_error(*, cog_name: str, callback: str, error: Exception) -> str:
    """Log a failed cog callback and build the message shown in the dashboard.

    The change is already committed at this point, so the message makes clear
    that the value was saved but the bot could not apply it yet.

    Args:
        cog_name (str): Cog name
        callback (str): Name of the cog method that raised
        error (Exception): Exception raised by the callback

    Returns:
        str: User-facing error message
    """
    logger.error(f"Error in {callback} of {cog_name}: {error}", exc_info=error)
    return (
        f"Saved, but the bot could not apply the change: {error}. "
        "It will be retried when the bot restarts; check the bot logs for details."
    )


async def _notify_cog_config_changed(
    request: Request, guild_id: int, cog_name: str, keys: list[str]
) -> str | None:
    """Notify a cog that configurations changed.

    If the cog implements the `on_config_changed` method, it will be called with
    the guild_id and the keys that changed. The cog decides what to do.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        keys (list[str]): List of configuration keys that changed

    Returns:
        str | None: Error message when the cog failed to apply the change, else None
    """
    bot = request.app.state.bot
    if not bot:
        return None

    guild = bot.get_guild(guild_id)
    if not guild:
        return None

    # Find the cog by name (convert snake_case to CamelCase + Cog)
    # For example: "verification" -> "VerificationCog"
    cog_class_name = cog_name.title().replace("_", "") + "Cog"
    cog = bot.get_cog(cog_class_name)

    if not cog:
        return None

    try:
        await cog.on_config_changed(guild=guild, keys=keys)
    except Exception as e:
        return _cog_apply_error(cog_name=cog_name, callback="on_config_changed", error=e)
    return None


async def _notify_cog_toggled(
    request: Request, guild_id: int, cog_name: str, enabled: bool
) -> str | None:
    """Notify a cog that it was enabled or disabled.

    If the cog implements the `on_cog_toggled` method, it will be called with
    the guild and the new state.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        enabled (bool): True if enabled, False if disabled

    Returns:
        str | None: Error message when the cog failed to apply the change, else None
    """
    bot = request.app.state.bot
    if not bot:
        return None

    guild = bot.get_guild(guild_id)
    if not guild:
        return None

    cog_class_name = cog_name.title().replace("_", "") + "Cog"
    cog = bot.get_cog(cog_class_name)

    if not cog:
        return None

    try:
        await cog.on_cog_toggled(guild=guild, enabled=enabled)
    except Exception as e:
        return _cog_apply_error(cog_name=cog_name, callback="on_cog_toggled", error=e)
    return None


def _validate_channel_permissions(request: Request, guild_id: int, channel_id: int) -> str | None:
    """Validate that the bot has permissions to send messages in a channel.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        channel_id (int): Channel ID

    Returns:
        str | None: Error message or None if has permissions
    """
    bot = request.app.state.bot
    if not bot:
        return None  # Cannot validate without bot

    guild = bot.get_guild(guild_id)
    if not guild:
        return None  # Cannot validate without guild

    channel = guild.get_channel(channel_id)
    if not channel:
        return f"Channel with ID {channel_id} not found"

    # Get bot permissions in the channel
    bot_member = guild.get_member(bot.user.id)
    if not bot_member:
        return None  # Cannot validate

    permissions = channel.permissions_for(bot_member)
    if not permissions.send_messages:
        return (
            f"The bot doesn't have permission to send messages in #{channel.name}. "
            f"Add the 'Send Messages' permission to the bot in that channel."
        )

    return None


def _manageable_role_ids(option: ConfigOption, value: Any) -> list[int]:
    """Collect the role IDs in ``value`` that the bot must be able to manage.

    Args:
        option (ConfigOption): Option being saved
        value (Any): Converted value (int, list of ints or table rows)

    Returns:
        list[int]: Role IDs to check against the bot's hierarchy (empty when N/A)
    """
    if option.option_type == ConfigOptionType.TABLE:
        columns = [
            col["key"]
            for col in option.columns or []
            if col.get("type") == "role" and col.get("manageable_only")
        ]
        rows = value if isinstance(value, list) else []
        raw = [row.get(col) for row in rows if isinstance(row, dict) for col in columns]
    elif not option.manageable_only:
        return []
    elif option.option_type == ConfigOptionType.ROLE:
        raw = [value]
    elif option.option_type == ConfigOptionType.ROLE_LIST:
        raw = list(value) if isinstance(value, list) else []
    else:
        return []
    ids: list[int] = []
    for item in raw:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            ids.append(int(item))  # Legacy string IDs in table rows
        # Anything else (blank, junk) is left to the regular type validation
    return ids


def _validate_manageable_roles(
    request: Request, guild_id: int, option: ConfigOption, value: Any
) -> str | None:
    """Reject roles the bot cannot assign or remove (at or above its top role).

    Only applies to options (or table role columns) flagged ``manageable_only``;
    unknown role IDs are left to the regular validation.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        option (ConfigOption): Option being saved
        value (Any): Converted value

    Returns:
        str | None: Error message naming the offending roles, or None
    """
    bot = request.app.state.bot
    guild = bot.get_guild(guild_id) if bot else None
    if not guild:
        return None  # Cannot validate without the bot's view of the guild

    bot_top_role = guild.me.top_role
    roles = (guild.get_role(rid) for rid in _manageable_role_ids(option=option, value=value))
    too_high = [f"@{role.name}" for role in roles if role is not None and role >= bot_top_role]
    if not too_high:
        return None
    return (
        f"'{option.name}': the bot cannot manage {', '.join(too_high)}. "
        f"Move the bot's role above them or pick roles below it."
    )


def _prepare_option_value(
    request: Request,
    guild_id: int,
    option: ConfigOption,
    value: Any,
    locked_options: dict[str, Any],
) -> tuple[Any, str | None]:
    """Convert a submitted option value and run every check on it.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        option (ConfigOption): Option being saved
        value (Any): Raw submitted value
        locked_options (dict[str, Any]): Options locked by the deployment for this cog

    Returns:
        tuple[Any, str | None]: Converted value and the first error found, or None
    """
    # Locked options are hidden in the UI, but a crafted request must not
    # be able to write them either
    if option.key in locked_options:
        lock = locked_options[option.key]
        reason = lock.get("reason") if isinstance(lock, dict) else str(lock)
        return None, f"{option.key}: {reason or 'locked by the deployment configuration'}"

    try:
        converted_value = _convert_form_value(value, option.option_type, option=option)
    except ValueError as e:
        return None, f"{option.key}: {e}"

    # Channel permissions / role hierarchy checks need the live guild
    guild_error = _validate_option_value(
        request=request, guild_id=guild_id, option=option, value=converted_value
    )
    return converted_value, guild_error


def _validate_option_value(
    request: Request, guild_id: int, option: ConfigOption, value: Any
) -> str | None:
    """Run the guild-dependent checks on a converted option value.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        option (ConfigOption): Option being saved
        value (Any): Converted value

    Returns:
        str | None: First error found, or None
    """
    if value and option.option_type == ConfigOptionType.CHANNEL:
        return _validate_channel_permissions(request=request, guild_id=guild_id, channel_id=value)
    return _validate_manageable_roles(
        request=request, guild_id=guild_id, option=option, value=value
    )


def _parse_int(value: str) -> int:
    """Parse a whole number from form input.

    Args:
        value (str): Value as string

    Returns:
        int: Parsed number

    Raises:
        ValueError: If the value is not a whole number.
    """
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"'{value.strip()}' is not a valid number") from None


def _convert_form_value(
    value: str,
    option_type: ConfigOptionType,
    option: ConfigOption | None = None,
) -> Any:
    """Convert a form value to the correct type.

    Args:
        value (str): Value as string
        option_type (ConfigOptionType): Option type
        option (ConfigOption | None): Complete option (for TABLE with columns)

    Returns:
        Any: Converted value

    Raises:
        ValueError: If the value is not a string or is not a valid number for
            numeric option types.
    """
    if not isinstance(value, str):
        raise ValueError("value must be a string")

    # For STRING, TEXTAREA and TEXT_CHOICE, preserve empty strings
    # (allows "clearing" a value or selecting empty option)
    preserve_empty_types = (
        ConfigOptionType.STRING,
        ConfigOptionType.TEXTAREA,
        ConfigOptionType.TEXT_CHOICE,
    )
    if option_type in preserve_empty_types:
        return value

    if not value:
        return None

    match option_type:
        case ConfigOptionType.INTEGER | ConfigOptionType.CHANNEL | ConfigOptionType.ROLE:
            return _parse_int(value)
        case ConfigOptionType.BOOLEAN:
            return value.lower() in ("true", "1", "on", "yes")
        case ConfigOptionType.CHANNEL_LIST | ConfigOptionType.ROLE_LIST:
            return [_parse_int(v) for v in value.split(",") if v.strip()]
        case ConfigOptionType.TABLE:
            # Limit JSON size to prevent DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"JSON too large: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in TABLE config: {e}")
                return None

            # Validate that data is a list
            if not isinstance(data, list):
                logger.warning("TABLE config must be a list")
                return None

            # Process rows
            if option and option.columns:
                valid_keys = {col["key"] for col in option.columns}
                int_columns = {
                    col["key"] for col in option.columns if col.get("type") in ("role", "channel")
                }

                cleaned_data = []
                for row in data:
                    if not isinstance(row, dict):
                        continue

                    # Filter only valid keys
                    cleaned_row = {k: v for k, v in row.items() if k in valid_keys}

                    # Convert role/channel columns to integers
                    for col_key in int_columns:
                        if col_key in cleaned_row and cleaned_row[col_key]:
                            col_value = cleaned_row[col_key]
                            # Validate type before converting
                            if isinstance(col_value, int):
                                pass  # Already int
                            elif isinstance(col_value, str) and col_value.isdigit():
                                cleaned_row[col_key] = int(col_value)
                            else:
                                # Invalid value, remove the key
                                cleaned_row.pop(col_key, None)

                    cleaned_data.append(cleaned_row)

                return cleaned_data

            return data
        case ConfigOptionType.EMBED:
            # Limit JSON size to prevent DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"EMBED JSON too large: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in EMBED config: {e}")
                return None

            # Validate that data is a dictionary
            if not isinstance(data, dict):
                logger.warning("EMBED config must be a dictionary")
                return None

            # Validate embed structure
            valid_embed_keys = {
                "title",
                "description",
                "color",
                "thumbnail_url",
                "image_url",
                "footer_text",
                "footer_icon_url",
                "sections",
            }
            embed_data: dict[str, Any] = {k: v for k, v in data.items() if k in valid_embed_keys}

            # Validate URLs: must be placeholder {xxx} or start with http
            for url_key in ["thumbnail_url", "image_url", "footer_icon_url"]:
                url_value = embed_data.get(url_key)
                if not url_value or not isinstance(url_value, str):
                    continue
                url_value = url_value.strip()
                if not url_value:
                    continue
                is_placeholder = url_value.startswith("{") and url_value.endswith("}")
                is_http_url = url_value.startswith(("http://", "https://"))
                if is_placeholder or is_http_url:
                    continue
                embed_data.pop(url_key, None)
                logger.warning(f"Invalid URL in {url_key}: must be placeholder or http URL")

            # Validate that sections is a list if present
            if "sections" in embed_data:
                if not isinstance(embed_data["sections"], list):
                    embed_data["sections"] = []

            return embed_data
        case ConfigOptionType.EMBED_SECTIONS:
            # Limit JSON size to prevent DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"EMBED_SECTIONS JSON too large: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in EMBED_SECTIONS config: {e}")
                return None

            # Handle both list and dict with "sections" key
            if isinstance(data, dict) and "sections" in data:
                data = data["sections"]

            if not isinstance(data, list):
                logger.warning("EMBED_SECTIONS config must be a list")
                return None

            return data
        case _:
            return value
