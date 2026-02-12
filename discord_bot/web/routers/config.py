"""Router para configuración de servidores."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.web.dependencies import DbSession, RequireAuth, require_guild_access

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
    schema_service = get_config_schema_service()
    config_service = ConfigService(session)

    schemas = schema_service.get_all_schemas()
    enabled_cogs = await config_service.get_enabled_cogs(guild_id)

    cogs_data = []
    for cog_name, schema in sorted(schemas.items(), key=lambda x: x[1].display_name):
        is_enabled = enabled_cogs.get(cog_name, True)
        cogs_data.append(
            {
                "name": cog_name,
                "display_name": schema.display_name,
                "description": schema.description,
                "icon": schema.icon or "⚙️",
                "enabled": is_enabled,
                "options_count": len(schema.options),
            }
        )

    guild_info = _get_guild_info(user, guild_id)
    templates = get_templates(request)

    return templates.TemplateResponse(
        request=request,
        name="guild_config.html",
        context={
            "user": user,
            "guild": guild_info,
            "guild_id": guild_id,
            "cogs": cogs_data,
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
            # Get text channels
            channels = [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "category": ch.category.name if ch.category else None,
                }
                for ch in discord_guild.text_channels
            ]
            channels.sort(key=lambda c: (c["category"] or "", c["name"]))

            # Get roles (exclude @everyone)
            roles = [
                {"id": r.id, "name": r.name, "color": str(r.color)}
                for r in discord_guild.roles
                if r.name != "@everyone"
            ]
            roles.sort(key=lambda r: r["name"].lower())

    options_data = []
    for opt in schema.options:
        current_value = config_values.get(opt.key, opt.default)

        # Resolve display name for channel/role values
        display_value = current_value
        if current_value and discord_guild:
            if opt.option_type == ConfigOptionType.CHANNEL:
                ch = discord_guild.get_channel(current_value)
                display_value = f"#{ch.name}" if ch else f"ID: {current_value}"
            elif opt.option_type == ConfigOptionType.ROLE:
                role = discord_guild.get_role(current_value)
                display_value = f"@{role.name}" if role else f"ID: {current_value}"
            elif opt.option_type == ConfigOptionType.CHANNEL_LIST and isinstance(
                current_value, list
            ):
                names = []
                for ch_id in current_value:
                    ch = discord_guild.get_channel(ch_id)
                    names.append(f"#{ch.name}" if ch else f"ID: {ch_id}")
                display_value = ", ".join(names) if names else None
            elif opt.option_type == ConfigOptionType.ROLE_LIST and isinstance(current_value, list):
                names = []
                for r_id in current_value:
                    role = discord_guild.get_role(r_id)
                    names.append(f"@{role.name}" if role else f"ID: {r_id}")
                display_value = ", ".join(names) if names else None

        options_data.append(
            {
                "key": opt.key,
                "name": opt.name,
                "description": opt.description,
                "type": opt.option_type.value,
                "value": current_value,
                "display_value": display_value,
                "default": opt.default,
                "required": opt.required,
                "choices": opt.choices,
                "min_value": opt.min_value,
                "max_value": opt.max_value,
                "max_length": opt.max_length,
            }
        )

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="partials/cog_settings.html",
        context={
            "guild_id": guild_id,
            "cog_name": cog_name,
            "schema": {
                "display_name": schema.display_name,
                "description": schema.description,
                "icon": schema.icon or "⚙️",
            },
            "options": options_data,
            "enabled": is_enabled,
            "channels": channels,
            "roles": roles,
            "ConfigOptionType": ConfigOptionType,
        },
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
    config_service = ConfigService(session)
    current = await config_service.is_cog_enabled(guild_id, cog_name)
    await config_service.set_cog_enabled(guild_id, cog_name, not current)

    return await cog_settings(request, guild_id, cog_name, user, session)


@router.post("/{guild_id}/cog/{cog_name}/option/{key}", response_class=HTMLResponse)
async def update_option(
    request: Request,
    guild_id: int,
    cog_name: str,
    key: str,
    value: Annotated[str, Form()],
    user: GuildAccess,
    session: DbSession,
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

    converted_value = _convert_form_value(value, option.option_type)

    success, error = await config_service.set_value(guild_id, cog_name, key, converted_value)

    if not success:
        logger.warning(f"Error al guardar configuración: {error}")

    return await cog_settings(request, guild_id, cog_name, user, session)


@router.post("/{guild_id}/cog/{cog_name}/reset", response_class=HTMLResponse)
async def reset_cog_config(
    request: Request,
    guild_id: int,
    cog_name: str,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Reiniciar la configuración de un cog a valores por defecto.

    Args:
        request (Request): Request de FastAPI
        guild_id (int): ID del guild
        cog_name (str): Nombre del cog
        user (GuildAccess): Usuario con acceso verificado
        session (DbSession): Sesión de base de datos

    Returns:
        HTMLResponse: Partial actualizado
    """
    config_service = ConfigService(session)
    await config_service.reset_config(guild_id, cog_name)

    return await cog_settings(request, guild_id, cog_name, user, session)


def _convert_form_value(value: str, option_type: ConfigOptionType) -> Any:
    """Convertir un valor de formulario al tipo correcto.

    Args:
        value (str): Valor como string
        option_type (ConfigOptionType): Tipo de opción

    Returns:
        Any: Valor convertido
    """
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
            if not value:
                return []
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        case _:
            return value
