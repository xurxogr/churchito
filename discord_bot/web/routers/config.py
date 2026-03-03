"""Router para configuración de servidores."""

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
from discord_bot.common.services.embed_builder import GLOBAL_PLACEHOLDERS
from discord_bot.web.dependencies import DbSession, RequireAuth, require_guild_access
from discord_bot.web.middleware import get_csrf_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guild", tags=["config"])


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


async def guild_access_dep(
    request: Request,
    guild_id: Annotated[int, Path()],
    user: RequireAuth,
) -> dict[str, Any]:
    """Dependencia para verificar acceso al guild.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        user (RequireAuth): Usuario autenticado

    Returns:
        dict[str, Any]: Datos del usuario si tiene acceso
    """
    return await require_guild_access(request, guild_id, user)


GuildAccess = Annotated[dict[str, Any], Depends(guild_access_dep)]


def _get_guild_info(user: dict[str, Any], guild_id: int) -> dict[str, Any]:
    """Obtener información del guild.

    Args:
        user (dict[str, Any]): Usuario autenticado
        guild_id (int): ID del guild

    Returns:
        dict[str, Any]: Información del guild
    """
    guilds: list[dict[str, Any]] = user.get("guilds", [])
    for guild in guilds:
        if int(guild.get("id", 0)) == guild_id:
            return guild
    return {"id": str(guild_id), "name": f"Servidor {guild_id}"}


def _format_relative_time(delta: timedelta) -> str:
    """Formatear un timedelta como texto relativo en español.

    Args:
        delta: Diferencia de tiempo

    Returns:
        str: Texto como "hace 2 días", "hace 3 meses", etc.
    """
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "hace unos segundos"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"hace {minutes} minuto{'s' if minutes != 1 else ''}"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"hace {hours} hora{'s' if hours != 1 else ''}"
    elif total_seconds < 2592000:  # ~30 days
        days = total_seconds // 86400
        return f"hace {days} día{'s' if days != 1 else ''}"
    elif total_seconds < 31536000:  # ~365 days
        months = total_seconds // 2592000
        return f"hace {months} mes{'es' if months != 1 else ''}"
    else:
        years = total_seconds // 31536000
        return f"hace {years} año{'s' if years != 1 else ''}"


@router.get("/{guild_id}", response_class=HTMLResponse)
async def guild_config(
    request: Request,
    guild_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Página de configuración de un servidor.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Página de configuración
    """
    # Verify bot is in this guild
    bot = request.app.state.bot
    if not bot or not bot.get_guild(guild_id):
        raise HTTPException(
            status_code=404,
            detail="El bot no está en este servidor",
        )

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
        return (priority, schema.display_name)

    for cog_name, schema in sorted(schemas.items(), key=cog_sort_key):
        is_enabled = enabled_cogs.get(cog_name, False)
        cogs_data.append(
            {
                "name": cog_name,
                "display_name": schema.display_name,
                "description": schema.description,
                "icon": schema.icon or "⚙️",
                "enabled": is_enabled,
                "toggleable": schema.toggleable,
                "options_count": len(schema.options),
            }
        )

    guild_info = _get_guild_info(user, guild_id)
    templates = get_templates(request)

    return templates.TemplateResponse(
        request=request,
        name="guild_config.html",
        context={
            **base_context(request),
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
) -> HTMLResponse:
    """Renderizar el partial de configuración de un cog.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        session: Sesión de base de datos
        user: Usuario autenticado (para preview de placeholders)
        error (str | None): Mensaje de error opcional

    Returns:
        HTMLResponse: Partial HTML con la configuración del cog
    """
    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    schema = schema_service.get_schema(cog_name)
    if not schema:
        raise HTTPException(status_code=404, detail="Cog no encontrado")

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

    options_data: list[dict[str, Any]] = []
    for opt in schema.options:
        # Skip locked options - they don't appear in the UI
        if opt.key in locked_options:
            continue

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

        options_data.append(
            {
                "key": opt.key,
                "name": opt.name,
                "description": opt.description,
                "type": opt.option_type.value,
                "value": template_value,
                "display_value": display_value,
                "default": opt.default,
                "required": opt.required,
                "section": opt.section,
                "group": opt.group,
                "choices": opt.choices,
                "min_value": opt.min_value,
                "max_value": opt.max_value,
                "max_length": opt.max_length,
                "placeholders": opt.placeholders,
                "columns": opt.columns,
            }
        )

    templates = get_templates(request)
    guild_name = discord_guild.name if discord_guild else f"Servidor {guild_id}"
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
        "user_name": user.get("username", "Usuario") if user else "Usuario",
        "user_mention": f"@{user.get('username', 'Usuario')}" if user else "@Usuario",
        "user_id": str(user.get("id", "123456789")) if user else "123456789",
        "user_avatar_url": (
            f"https://cdn.discordapp.com/avatars/{user.get('id')}/{user.get('avatar')}.png"
            if user and user.get("avatar")
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
        "user_joined_server": user_joined_server or "01/01/2024 12:00",
        "user_joined_server_relative": user_joined_server_relative or "hace 2 meses",
        "user_joined_discord": user_joined_discord or "01/06/2020 15:00",
        "user_joined_discord_relative": user_joined_discord_relative or "hace 4 años",
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "status": "📷 Esperando capturas",
        "verification_type": "Miembro",
        "username": user.get("username", "Usuario") if user else "Usuario",
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

    return templates.TemplateResponse(
        request=request,
        name="partials/cog_settings.html",
        context={
            **base_context(request),
            "guild_id": guild_id,
            "guild_name": guild_name,
            "cog_name": cog_name,
            "schema": {
                "display_name": schema.display_name,
                "description": schema.description,
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
    """Obtener el partial de configuración de un cog (HTMX).

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Partial HTML con la configuración del cog
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
    """Alternar el estado de habilitación de un cog.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Partial actualizado
    """
    # Validar que el cog existe antes de cualquier operación DB
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(cog_name):
        raise HTTPException(status_code=404, detail="Cog no encontrado")

    config_service = ConfigService(session)
    current = await config_service.is_cog_enabled(guild_id, cog_name)
    new_state = not current
    await config_service.set_cog_enabled(guild_id, cog_name, new_state)

    # Commit para que el cog vea el cambio en su propia sesión
    await session.commit()

    # Notificar al cog del cambio
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
    """Actualizar una opción de configuración.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        key (str): Clave de la opción
        value (str): Nuevo valor (como string del formulario)
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Partial actualizado
    """
    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    option = schema_service.get_option(cog_name, key)
    if not option:
        raise HTTPException(status_code=404, detail="Opción no encontrada")

    converted_value = _convert_form_value(value, option.option_type, option=option)

    # Validar permisos del bot para canales
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
        logger.warning(f"Error al guardar configuración: {validation_error}")
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error=validation_error,
        )

    # Commit para que el cog vea los cambios en su propia sesión
    await session.commit()

    # Notificar al cog que una configuración cambió
    await _notify_cog_config_changed(request=request, guild_id=guild_id, cog_name=cog_name, key=key)

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
    )


@router.post("/{guild_id}/cog/{cog_name}/reload", response_class=HTMLResponse)
async def reload_cog(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Recargar un cog (reload de la extensión).

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Partial actualizado
    """
    # Validar que el cog existe antes de cualquier operación
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(cog_name):
        raise HTTPException(status_code=404, detail="Cog no encontrado")

    # El cog "bot" no se puede recargar
    if cog_name == "bot":
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error="El módulo 'bot' no se puede recargar",
        )

    bot = request.app.state.bot
    if not bot:
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error="Bot no disponible",
        )

    extension_name = f"discord_bot.{cog_name}.cog"
    try:
        await bot.reload_extension(extension_name)
        logger.info(f"Cog {cog_name} recargado por usuario {user.get('id')}")
    except Exception as e:
        logger.error(f"Error al recargar cog {cog_name}: {e}")
        return await _render_cog_settings(
            request=request,
            guild_id=guild_id,
            cog_name=cog_name,
            session=session,
            user=user,
            error=f"Error al recargar: {e}",
        )

    return await _render_cog_settings(
        request=request,
        guild_id=guild_id,
        cog_name=cog_name,
        session=session,
        user=user,
    )


async def _notify_cog_config_changed(
    request: Request, guild_id: int, cog_name: str, key: str
) -> None:
    """Notificar a un cog que una configuración cambió.

    Si el cog implementa el método `on_config_changed`, se llamará con
    el guild_id y la key que cambió. El cog decide qué hacer.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        key (str): Clave de configuración que cambió
    """
    bot = request.app.state.bot
    if not bot:
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    # Buscar el cog por nombre (convertir snake_case a CamelCase + Cog)
    # Por ejemplo: "verification" -> "VerificationCog"
    cog_class_name = cog_name.title().replace("_", "") + "Cog"
    cog = bot.get_cog(cog_class_name)

    if not cog:
        return

    try:
        await cog.on_config_changed(guild=guild, key=key)
    except Exception as e:
        logger.error(f"Error en on_config_changed de {cog_name}: {e}")


async def _notify_cog_toggled(
    request: Request, guild_id: int, cog_name: str, enabled: bool
) -> None:
    """Notificar a un cog que fue habilitado o deshabilitado.

    Si el cog implementa el método `on_cog_toggled`, se llamará con
    el guild y el nuevo estado.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        enabled (bool): True si fue habilitado, False si fue deshabilitado
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
        logger.error(f"Error en on_cog_toggled de {cog_name}: {e}")


def _validate_channel_permissions(request: Request, guild_id: int, channel_id: int) -> str | None:
    """Validar que el bot tiene permisos para enviar mensajes en un canal.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        channel_id (int): ID del canal

    Returns:
        str | None: Mensaje de error o None si tiene permisos
    """
    bot = request.app.state.bot
    if not bot:
        return None  # No podemos validar sin bot

    guild = bot.get_guild(guild_id)
    if not guild:
        return None  # No podemos validar sin guild

    channel = guild.get_channel(channel_id)
    if not channel:
        return f"Canal con ID {channel_id} no encontrado"

    # Obtener permisos del bot en el canal
    bot_member = guild.get_member(bot.user.id)
    if not bot_member:
        return None  # No podemos validar

    permissions = channel.permissions_for(bot_member)
    if not permissions.send_messages:
        return (
            f"El bot no tiene permisos para enviar mensajes en #{channel.name}. "
            f"Agrega el permiso 'Enviar mensajes' al bot en ese canal."
        )

    return None


def _convert_form_value(
    value: str,
    option_type: ConfigOptionType,
    option: ConfigOption | None = None,
) -> Any:
    """Convertir un valor de formulario al tipo correcto.

    Args:
        value (str): Valor como string
        option_type (ConfigOptionType): Tipo de opción
        option (ConfigOption | None): Opción completa (para TABLE con columns)

    Returns:
        Any: Valor convertido
    """
    # Para STRING, TEXTAREA y TEXT_CHOICE, preservar cadenas vacias
    # (permite "limpiar" un valor o seleccionar opción vacía)
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
            return value.lower() in ("true", "1", "on", "yes", "sí")
        case ConfigOptionType.CHANNEL | ConfigOptionType.ROLE:
            return int(value)
        case ConfigOptionType.CHANNEL_LIST | ConfigOptionType.ROLE_LIST:
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        case ConfigOptionType.TABLE:
            import json

            # Limitar tamaño del JSON para prevenir DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"JSON demasiado grande: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON inválido en TABLE config: {e}")
                return None

            # Validar que data es una lista
            if not isinstance(data, list):
                logger.warning("TABLE config debe ser una lista")
                return None

            # Procesar filas
            if option and option.columns:
                valid_keys = {col["key"] for col in option.columns}
                int_columns = {
                    col["key"] for col in option.columns if col.get("type") in ("role", "channel")
                }

                cleaned_data = []
                for row in data:
                    if not isinstance(row, dict):
                        continue

                    # Filtrar solo claves válidas
                    cleaned_row = {k: v for k, v in row.items() if k in valid_keys}

                    # Convertir columnas de role/channel a enteros
                    for col_key in int_columns:
                        if col_key in cleaned_row and cleaned_row[col_key]:
                            col_value = cleaned_row[col_key]
                            # Validar tipo antes de convertir
                            if isinstance(col_value, int):
                                pass  # Ya es int
                            elif isinstance(col_value, str) and col_value.isdigit():
                                cleaned_row[col_key] = int(col_value)
                            else:
                                # Valor inválido, eliminar la clave
                                cleaned_row.pop(col_key, None)

                    cleaned_data.append(cleaned_row)

                return cleaned_data

            return data
        case ConfigOptionType.EMBED:
            import json

            # Limitar tamaño del JSON para prevenir DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"JSON de EMBED demasiado grande: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON inválido en EMBED config: {e}")
                return None

            # Validar que data es un diccionario
            if not isinstance(data, dict):
                logger.warning("EMBED config debe ser un diccionario")
                return None

            # Validar estructura del embed
            valid_embed_keys = {
                "title",
                "color",
                "thumbnail_url",
                "image_url",
                "footer_text",
                "footer_icon_url",
                "sections",
            }
            embed_data: dict[str, Any] = {k: v for k, v in data.items() if k in valid_embed_keys}

            # Validar que sections es una lista si existe
            if "sections" in embed_data:
                if not isinstance(embed_data["sections"], list):
                    embed_data["sections"] = []

            return embed_data
        case ConfigOptionType.EMBED_SECTIONS:
            import json

            # Limitar tamaño del JSON para prevenir DoS
            max_json_size = 100_000  # 100KB
            if len(value) > max_json_size:
                logger.warning(f"JSON de EMBED_SECTIONS demasiado grande: {len(value)} bytes")
                return None

            try:
                data = json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON inválido en EMBED_SECTIONS config: {e}")
                return None

            # Validar que data es una lista
            if not isinstance(data, list):
                logger.warning("EMBED_SECTIONS config debe ser una lista")
                return None

            return data
        case _:
            return value
