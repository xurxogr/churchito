"""Router for server configuration."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.embed_builder import COLOR_TAGS, GLOBAL_PLACEHOLDERS
from discord_bot.i18n import get_i18n_service
from discord_bot.web.dependencies import DbSession, RequireAuth, require_guild_access
from discord_bot.web.middleware import get_csrf_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guild", tags=["config"])


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


def _format_relative_time(delta: timedelta) -> str:
    """Format a timedelta as relative text in English.

    Args:
        delta: Time difference

    Returns:
        str: Text like "2 days ago", "3 months ago", etc.
    """
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "a few seconds ago"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif total_seconds < 2592000:  # ~30 days
        days = total_seconds // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif total_seconds < 31536000:  # ~365 days
        months = total_seconds // 2592000
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = total_seconds // 31536000
        return f"{years} year{'s' if years != 1 else ''} ago"


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
        session: Database session
        user: Authenticated user (for placeholder preview)
        error (str | None): Optional error message
        lang (str | None): Language code

    Returns:
        HTMLResponse: Partial HTML with cog configuration
    """
    # Get language from browser if not provided
    if lang is None:
        lang = get_browser_language(request)

    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    schema = schema_service.get_schema(cog_name)
    if not schema:
        raise HTTPException(status_code=404, detail="Cog not found")

    config_values = await config_service.get_all_config(guild_id, cog_name)
    is_enabled = await config_service.is_cog_enabled(guild_id, cog_name)

    # Get bot and guild for resolving channel/role names
    bot = request.app.state.bot
    discord_guild = None
    channels: list[dict[str, Any]] = []
    roles: list[dict[str, Any]] = []

    if bot:
        discord_guild = bot.get_guild(guild_id)
        if discord_guild:
            # Get bot member for permission checks
            bot_member = discord_guild.get_member(bot.user.id)

            # Get text channels (only those where bot can send messages)
            for ch in discord_guild.text_channels:
                can_send = True
                if bot_member:
                    permissions = ch.permissions_for(bot_member)
                    can_send = permissions.send_messages

                if can_send:
                    channels.append(
                        {
                            # Use string IDs to avoid JS precision loss with snowflakes
                            "id": str(ch.id),
                            "name": ch.name,
                            "category": ch.category.name if ch.category else None,
                        }
                    )
            channels.sort(key=lambda c: (c["category"] or "", c["name"]))

            # Get roles (exclude @everyone and roles above bot's highest role)
            bot_top_role = discord_guild.me.top_role
            roles = [
                # Use string IDs to avoid JS precision loss with snowflakes
                {"id": str(r.id), "name": r.name, "color": str(r.color)}
                for r in discord_guild.roles
                if r.name != "@everyone" and r < bot_top_role
            ]
            roles.sort(key=lambda r: r["name"].lower())

    # Check for locked options from cog settings
    locked_options: dict[str, dict[str, Any]] = {}
    if bot:
        cog_class_name = cog_name.title().replace("_", "") + "Cog"
        cog = bot.get_cog(cog_class_name)
        if cog:
            try:
                locked_options = cog.get_locked_options()
            except Exception as e:
                logger.warning(f"Error getting locked options from {cog_name}: {e}")

    # Get translations for this cog
    i18n = get_i18n_service()
    cog_translations = i18n.get_cog_translations(cog_name, lang)
    options_trans = cog_translations.get("options", {})
    groups_trans = cog_translations.get("groups", {})
    sections_trans = cog_translations.get("sections", {})
    choices_trans = cog_translations.get("choices", {})

    options_data: list[dict[str, Any]] = []
    for opt in schema.options:
        # Skip locked options - they don't appear in the UI
        if opt.key in locked_options:
            continue

        # Get option translations
        opt_trans = options_trans.get(opt.key, {})
        translated_name = opt_trans.get("name", opt.name)
        translated_desc = opt_trans.get("description", opt.description)
        translated_section = sections_trans.get(opt.section, opt.section) if opt.section else None
        translated_group = groups_trans.get(opt.group, opt.group) if opt.group else None

        raw_value = config_values.get(opt.key, opt.default)

        # Resolve display name for channel/role values (using raw int IDs)
        display_value = raw_value
        if raw_value and discord_guild:
            if opt.option_type == ConfigOptionType.CHANNEL:
                ch = discord_guild.get_channel(raw_value)
                display_value = f"#{ch.name}" if ch else f"ID: {raw_value}"
            elif opt.option_type == ConfigOptionType.ROLE:
                role = discord_guild.get_role(raw_value)
                display_value = f"@{role.name}" if role else f"ID: {raw_value}"
            elif opt.option_type == ConfigOptionType.CHANNEL_LIST and isinstance(raw_value, list):
                names: list[str] = []
                for ch_id in raw_value:
                    ch = discord_guild.get_channel(ch_id)
                    names.append(f"#{ch.name}" if ch else f"ID: {ch_id}")
                display_value = ", ".join(names) if names else None
            elif opt.option_type == ConfigOptionType.ROLE_LIST and isinstance(raw_value, list):
                role_names: list[str] = []
                for r_id in raw_value:
                    role = discord_guild.get_role(r_id)
                    role_names.append(f"@{role.name}" if role else f"ID: {r_id}")
                display_value = ", ".join(role_names) if role_names else None

        # Convert channel/role IDs to strings for template comparison
        # (dropdown options use string IDs to avoid JS precision loss)
        template_value = raw_value
        if raw_value is not None:
            if opt.option_type in (ConfigOptionType.CHANNEL, ConfigOptionType.ROLE):
                template_value = str(raw_value)
            elif opt.option_type in (ConfigOptionType.CHANNEL_LIST, ConfigOptionType.ROLE_LIST):
                if isinstance(raw_value, list):
                    template_value = [str(v) for v in raw_value]

        # Translate choices if present
        translated_choices = None
        if opt.choices:
            translated_choices = []
            for label, value in opt.choices:
                translated_label = label
                # Check option-specific choices translations first
                opt_choices_trans = opt_trans.get("choices", {})
                if label in opt_choices_trans:
                    translated_label = opt_choices_trans[label]
                else:
                    # Search through all choice groups in cog translations
                    for choice_group in choices_trans.values():
                        if isinstance(choice_group, dict) and label in choice_group:
                            translated_label = choice_group[label]
                            break
                translated_choices.append((translated_label, value))

        # Translate table columns if present
        translated_columns = None
        if opt.columns:
            columns_trans = cog_translations.get("columns", {})
            translated_columns = []
            for col in opt.columns:
                col_copy = col.copy()
                col_key = col.get("key", "")
                if col_key in columns_trans:
                    col_copy["name"] = columns_trans[col_key]
                translated_columns.append(col_copy)

        options_data.append(
            {
                "key": opt.key,
                "name": translated_name,
                "description": translated_desc,
                "type": opt.option_type.value,
                "value": template_value,
                "display_value": display_value,
                "default": opt.default,
                "required": opt.required,
                "section": translated_section,
                "group": translated_group,
                "choices": translated_choices,
                "min_value": opt.min_value,
                "max_value": opt.max_value,
                "max_length": opt.max_length,
                "placeholders": opt.placeholders,
                "columns": translated_columns,
            }
        )

    templates = get_templates(request)
    guild_name = discord_guild.name if discord_guild else f"Server {guild_id}"
    member_count = discord_guild.member_count if discord_guild else 0

    # Get member from guild for join date info
    member = None
    if discord_guild and user:
        user_id = user.get("id")
        if user_id:
            member = discord_guild.get_member(int(user_id))

    # Build preview data for placeholders
    now = datetime.now(UTC)

    # Format join dates if member is available
    user_joined_server = ""
    user_joined_server_relative = ""
    user_joined_discord = ""
    user_joined_discord_relative = ""

    if member:
        if member.joined_at:
            user_joined_server = member.joined_at.strftime("%d/%m/%Y %H:%M")
            delta = now - member.joined_at
            user_joined_server_relative = _format_relative_time(delta)

        if member.created_at:
            user_joined_discord = member.created_at.strftime("%d/%m/%Y %H:%M")
            delta = now - member.created_at
            user_joined_discord_relative = _format_relative_time(delta)

    preview_data = {
        "server_name": guild_name,
        "server_id": str(guild_id),
        "server_member_count": str(member_count),
        "user_name": user.get("username", "User") if user else "User",
        "user_mention": f"@{user.get('username', 'User')}" if user else "@User",
        "user_id": str(user.get("id", "123456789")) if user else "123456789",
        "user_avatar_url": (
            f"https://cdn.discordapp.com/avatars/{user.get('id')}/{user.get('avatar')}.png"
            if user and user.get("avatar")
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
        "user_joined_server": user_joined_server or "01/01/2024 12:00",
        "user_joined_server_relative": user_joined_server_relative or "2 months ago",
        "user_joined_discord": user_joined_discord or "01/06/2020 15:00",
        "user_joined_discord_relative": user_joined_discord_relative or "4 years ago",
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "status": "📷 Waiting for screenshots",
        "verification_type": "Member",
        "username": user.get("username", "User") if user else "User",
        # Player info placeholders (for verification API response preview)
        "name": "PlayerName",
        "regiment": "82DK",
        "level": "45",
        "faction": "colonial",
        "shard": "ABLE",
        "time": "268, 07:41",
        "war": "115",
        "war_time": "278, 08:34",
    }

    # Get translated schema display name and description
    translated_display_name = cog_translations.get("display_name", schema.display_name)
    translated_description = cog_translations.get("description", schema.description)

    return templates.TemplateResponse(
        request=request,
        name="partials/cog_settings.html",
        context={
            **base_context(request, lang),
            "guild_id": guild_id,
            "guild_name": guild_name,
            "cog_name": cog_name,
            "schema": {
                "display_name": translated_display_name,
                "description": translated_description,
                "icon": schema.icon or "⚙️",
                "toggleable": schema.toggleable,
            },
            "options": options_data,
            "enabled": is_enabled,
            "channels": channels,
            "roles": roles,
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
    current = await config_service.is_cog_enabled(guild_id, cog_name)
    new_state = not current
    await config_service.set_cog_enabled(guild_id, cog_name, new_state)

    # Commit so the cog sees the change in its own session
    await session.commit()

    # Notify the cog of the change
    await _notify_cog_toggled(
        request=request, guild_id=guild_id, cog_name=cog_name, enabled=new_state
    )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
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

    converted_value = _convert_form_value(value, option.option_type, option=option)

    # Validate bot permissions for channels
    if converted_value and option.option_type == ConfigOptionType.CHANNEL:
        permission_error = _validate_channel_permissions(
            request=request, guild_id=guild_id, channel_id=converted_value
        )
        if permission_error:
            return await _render_cog_settings(
                request=request,
                guild_id=guild_id,
                cog_name=cog_name,
                session=session,
                user=user,
                error=permission_error,
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

    # Notify the cog that a configuration changed
    await _notify_cog_config_changed(
        request=request, guild_id=guild_id, cog_name=cog_name, keys=[key]
    )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
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
        options_to_save: dict[str, str] = body.get("options", {})
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None

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

    # Save all options to DB first
    for key, value in options_to_save.items():
        option = schema_service.get_option(cog_name, key)
        if not option:
            errors.append(f"Option '{key}' not found")
            continue

        converted_value = _convert_form_value(value, option.option_type, option=option)

        # Validate channel permissions
        if converted_value and option.option_type == ConfigOptionType.CHANNEL:
            permission_error = _validate_channel_permissions(
                request=request, guild_id=guild_id, channel_id=converted_value
            )
            if permission_error:
                errors.append(permission_error)
                continue

        success, validation_error = await config_service.set_value(
            guild_id=guild_id, cog_name=cog_name, key=key, value=converted_value
        )

        if success:
            saved_keys.append(key)
        else:
            errors.append(f"{key}: {validation_error}")

    # Commit all changes at once
    await session.commit()

    # Notify cog once with all changed keys
    if saved_keys:
        await _notify_cog_config_changed(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            keys=saved_keys,
        )

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

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        user (GuildAccess): User with verified access
        session (DbSession): Database session

    Returns:
        HTMLResponse: Updated partial
    """
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


async def _notify_cog_config_changed(
    request: Request, guild_id: int, cog_name: str, keys: list[str]
) -> None:
    """Notify a cog that configurations changed.

    If the cog implements the `on_config_changed` method, it will be called with
    the guild_id and the keys that changed. The cog decides what to do.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        keys (list[str]): List of configuration keys that changed
    """
    bot = request.app.state.bot
    if not bot:
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    # Find the cog by name (convert snake_case to CamelCase + Cog)
    # For example: "verification" -> "VerificationCog"
    cog_class_name = cog_name.title().replace("_", "") + "Cog"
    cog = bot.get_cog(cog_class_name)

    if not cog:
        return

    try:
        await cog.on_config_changed(guild=guild, keys=keys)
    except Exception as e:
        logger.error(f"Error in on_config_changed of {cog_name}: {e}")


async def _notify_cog_toggled(
    request: Request, guild_id: int, cog_name: str, enabled: bool
) -> None:
    """Notify a cog that it was enabled or disabled.

    If the cog implements the `on_cog_toggled` method, it will be called with
    the guild and the new state.

    Args:
        request (Request): FastAPI request
        guild_id (int): Guild ID
        cog_name (str): Cog name
        enabled (bool): True if enabled, False if disabled
    """
    bot = request.app.state.bot
    if not bot:
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    cog_class_name = cog_name.title().replace("_", "") + "Cog"
    cog = bot.get_cog(cog_class_name)

    if not cog:
        return

    try:
        await cog.on_cog_toggled(guild=guild, enabled=enabled)
    except Exception as e:
        logger.error(f"Error in on_cog_toggled of {cog_name}: {e}")


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
    """
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
        case ConfigOptionType.INTEGER:
            return int(value)
        case ConfigOptionType.BOOLEAN:
            return value.lower() in ("true", "1", "on", "yes")
        case ConfigOptionType.CHANNEL | ConfigOptionType.ROLE:
            return int(value)
        case ConfigOptionType.CHANNEL_LIST | ConfigOptionType.ROLE_LIST:
            return [int(v.strip()) for v in value.split(",") if v.strip()]
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
