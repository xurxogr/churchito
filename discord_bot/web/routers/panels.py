"""Router for reaction panels management."""

import json
import logging
from typing import Annotated, Any

import discord
from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from discord_bot.i18n import get_i18n_service
from discord_bot.roles.models import PanelType, ReactionPanel
from discord_bot.roles.service import ReactionRolesService
from discord_bot.web.dependencies import DbSession, RequireAuth, require_guild_access
from discord_bot.web.middleware import get_csrf_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guild", tags=["panels"])


def get_browser_language(request: Request) -> str:
    """Get the language from the browser's Accept-Language header.

    Args:
        request: FastAPI request

    Returns:
        str: Language code ('en' or 'es', defaults to 'en')
    """
    i18n = get_i18n_service()
    accept_language = request.headers.get("Accept-Language", "")

    for part in accept_language.split(","):
        lang_part = part.split(";")[0].strip()
        base_lang = lang_part.split("-")[0].lower()

        if base_lang in i18n.SUPPORTED_LANGUAGES:
            return base_lang

    return i18n.DEFAULT_LANGUAGE


def get_templates(request: Request) -> Jinja2Templates:
    """Get the template engine."""
    templates: Jinja2Templates = request.app.state.templates
    return templates


async def guild_access_dep(
    request: Request,
    guild_id: Annotated[int, Path()],
    user: RequireAuth,
) -> dict[str, Any]:
    """Dependency to verify guild access."""
    return await require_guild_access(request=request, guild_id=guild_id, user=user)


GuildAccess = Annotated[dict[str, Any], Depends(guild_access_dep)]


def _format_embed_config(embed_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Format embed_config for template display.

    Converts integer colors to hex strings for the color picker.

    Args:
        embed_config: Raw embed config from database

    Returns:
        dict: Formatted embed config or None
    """
    if not embed_config:
        return None

    result = dict(embed_config)
    color = result.get("color")
    if isinstance(color, int):
        result["color"] = f"#{color:06X}"
    return result


def _panel_to_dict(panel: ReactionPanel, guild: Any) -> dict[str, Any]:
    """Convert a ReactionPanel to a dictionary for the template.

    Args:
        panel: ReactionPanel instance
        guild: Discord guild object

    Returns:
        dict: Panel data for template
    """
    channel = guild.get_channel(panel.channel_id) if guild else None
    channel_name = channel.name if channel else f"Unknown ({panel.channel_id})"

    return {
        "id": panel.id,
        "public_id": panel.public_id,
        "name": panel.name,
        "panel_type": panel.panel_type,
        "channel_id": str(panel.channel_id),
        "channel_name": channel_name,
        "message_id": panel.message_id,
        "is_posted": panel.message_id is not None,
        "mappings_count": len(panel.role_mappings),
        "role_mappings": panel.role_mappings,
        "required_roles": panel.required_roles,
        "dm_on_missing_role": panel.dm_on_missing_role,
        "dm_on_role_change": panel.dm_on_role_change,
        "exclusive_require_existing": panel.exclusive_require_existing,
        "embed_config": _format_embed_config(panel.embed_config),
    }


def _get_guild_data(
    request: Request, guild_id: int
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Get guild, channels, roles and emojis data.

    Args:
        request: FastAPI request
        guild_id: Guild ID

    Returns:
        tuple: (discord_guild, channels list, roles list, emojis list)
    """
    bot = request.app.state.bot
    discord_guild = bot.get_guild(guild_id) if bot else None

    channels = []
    roles = []
    emojis = []

    if discord_guild:
        bot_member = discord_guild.get_member(bot.user.id) if bot else None

        for ch in discord_guild.text_channels:
            can_send = True
            if bot_member:
                permissions = ch.permissions_for(bot_member)
                can_send = permissions.send_messages

            if can_send:
                channels.append(
                    {
                        "id": str(ch.id),
                        "name": ch.name,
                        "category": ch.category.name if ch.category else None,
                    }
                )
        channels.sort(key=lambda c: (c["category"] or "", c["name"]))

        bot_top_role = discord_guild.me.top_role
        roles = [
            {"id": str(r.id), "name": r.name, "color": str(r.color)}
            for r in discord_guild.roles
            if r.name != "@everyone" and r < bot_top_role
        ]
        roles.sort(key=lambda r: r["name"].lower())

        # Get guild custom emojis
        for emoji in discord_guild.emojis:
            emojis.append(
                {
                    "id": str(emoji.id),
                    "name": emoji.name,
                    "animated": emoji.animated,
                    "url": str(emoji.url),
                }
            )
        emojis.sort(key=lambda e: e["name"].lower())

    return discord_guild, channels, roles, emojis


@router.get("/{guild_id}/panels", response_class=HTMLResponse)
async def list_panels(
    request: Request,
    guild_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Get the panels list partial (HTMX).

    Args:
        request: FastAPI request
        guild_id: Guild ID
        user: User with verified access
        session: Database session

    Returns:
        HTMLResponse: Partial HTML with panels list
    """
    discord_guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=guild_id)

    service = ReactionRolesService(session)
    panels = await service.get_all_for_guild(guild_id)

    panels_data = [_panel_to_dict(panel=p, guild=discord_guild) for p in panels]

    lang = get_browser_language(request)
    i18n = get_i18n_service()

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="partials/panels_list.html",
        context={
            "root_path": request.scope.get("root_path", ""),
            "csrf_token": get_csrf_token(request),
            "guild_id": guild_id,
            "panels": panels_data,
            "channels": channels,
            "roles": roles,
            "emojis": emojis,
            "lang": lang,
            "panel_types": [
                {
                    "value": PanelType.TOGGLE,
                    "label": i18n.translate("ui.panels.panel_types.toggle", lang),
                },
                {
                    "value": PanelType.EXCLUSIVE,
                    "label": i18n.translate("ui.panels.panel_types.exclusive", lang),
                },
                {
                    "value": PanelType.VERIFY,
                    "label": i18n.translate("ui.panels.panel_types.verify", lang),
                },
            ],
        },
    )


@router.post("/{guild_id}/panels/create", response_class=HTMLResponse)
async def create_panel(
    request: Request,
    guild_id: int,
    user: GuildAccess,
    session: DbSession,
    name: Annotated[str, Form()],
    channel_id: Annotated[str, Form()],
    panel_type: Annotated[str, Form()],
    role_mappings: Annotated[str, Form()] = "[]",
    embed_config: Annotated[str, Form()] = "{}",
    dm_on_missing_role: Annotated[bool, Form()] = False,
    dm_on_role_change: Annotated[bool, Form()] = False,
    exclusive_require_existing: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Create a new panel with full configuration.

    Args:
        request: FastAPI request
        guild_id: Guild ID
        user: User with verified access
        session: Database session
        name: Panel name
        channel_id: Channel ID
        panel_type: Panel type
        role_mappings: JSON string of role mappings
        embed_config: JSON string of embed configuration
        dm_on_missing_role: Send DM when user lacks required role
        dm_on_role_change: Send DM when role is added/removed
        exclusive_require_existing: For exclusive panels, require existing role to switch

    Returns:
        HTMLResponse: Updated panels list
    """
    # Validate inputs
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Invalid panel name")

    try:
        channel_id_int = int(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid channel ID") from None

    if panel_type not in [t.value for t in PanelType]:
        raise HTTPException(status_code=400, detail="Invalid panel type")

    # Parse JSON fields
    try:
        mappings = json.loads(role_mappings) if role_mappings else []
        embed_cfg = json.loads(embed_config) if embed_config else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data") from None

    discord_guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=guild_id)
    guild_name = discord_guild.name if discord_guild else "Unknown"

    service = ReactionRolesService(session)

    # Check for duplicate name
    existing = await service.get_by_name(guild_id=guild_id, name=name)
    if existing:
        raise HTTPException(status_code=400, detail=f"Panel '{name}' already exists")

    # Create panel with all configuration
    user_id = int(user.get("id", 0))
    await service.create_panel(
        guild_id=guild_id,
        channel_id=channel_id_int,
        name=name,
        panel_type=PanelType(panel_type),
        created_by=user_id,
        guild_name=guild_name,
        role_mappings=mappings if mappings else None,
        embed_config=embed_cfg if embed_cfg else None,
        dm_on_missing_role=dm_on_missing_role,
        dm_on_role_change=dm_on_role_change,
        exclusive_require_existing=exclusive_require_existing,
    )
    await session.commit()

    # Return updated list
    return await list_panels(request=request, guild_id=guild_id, user=user, session=session)


@router.get("/{guild_id}/panels/{panel_id}/edit", response_class=HTMLResponse)
async def edit_panel_form(
    request: Request,
    guild_id: int,
    panel_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Get the panel edit form (HTMX).

    Args:
        request: FastAPI request
        guild_id: Guild ID
        panel_id: Panel ID
        user: User with verified access
        session: Database session

    Returns:
        HTMLResponse: Partial HTML with edit form
    """
    discord_guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=guild_id)

    service = ReactionRolesService(session)
    panel = await service.get_by_id(panel_id)

    if not panel or panel.guild_id != guild_id:
        raise HTTPException(status_code=404, detail="Panel not found")

    panel_data = _panel_to_dict(panel=panel, guild=discord_guild)

    lang = get_browser_language(request)
    i18n = get_i18n_service()

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="partials/panel_edit.html",
        context={
            "root_path": request.scope.get("root_path", ""),
            "csrf_token": get_csrf_token(request),
            "guild_id": guild_id,
            "panel": panel_data,
            "channels": channels,
            "roles": roles,
            "emojis": emojis,
            "lang": lang,
            "panel_types": [
                {
                    "value": PanelType.TOGGLE,
                    "label": i18n.translate("ui.panels.panel_types.toggle", lang),
                },
                {
                    "value": PanelType.EXCLUSIVE,
                    "label": i18n.translate("ui.panels.panel_types.exclusive", lang),
                },
                {
                    "value": PanelType.VERIFY,
                    "label": i18n.translate("ui.panels.panel_types.verify", lang),
                },
            ],
        },
    )


@router.post("/{guild_id}/panels/{panel_id}/update", response_class=HTMLResponse)
async def update_panel(
    request: Request,
    guild_id: int,
    panel_id: int,
    user: GuildAccess,
    session: DbSession,
    name: Annotated[str, Form()],
    channel_id: Annotated[str, Form()],
    panel_type: Annotated[str, Form()],
    role_mappings: Annotated[str, Form()] = "[]",
    required_roles: Annotated[str, Form()] = "[]",
    embed_config: Annotated[str, Form()] = "{}",
    dm_on_missing_role: Annotated[bool, Form()] = False,
    dm_on_role_change: Annotated[bool, Form()] = False,
    exclusive_require_existing: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Update a panel.

    Args:
        request: FastAPI request
        guild_id: Guild ID
        panel_id: Panel ID
        user: User with verified access
        session: Database session
        name: Panel name
        channel_id: Channel ID
        panel_type: Panel type
        role_mappings: JSON string of role mappings
        required_roles: JSON string of required role IDs
        embed_config: JSON string of embed configuration
        dm_on_missing_role: Send DM on missing role
        dm_on_role_change: Send DM on role change
        exclusive_require_existing: For exclusive panels, require existing role to switch

    Returns:
        HTMLResponse: Updated panels list
    """
    discord_guild, _, _, _ = _get_guild_data(request=request, guild_id=guild_id)
    guild_name = discord_guild.name if discord_guild else "Unknown"

    service = ReactionRolesService(session)
    panel = await service.get_by_id(panel_id)

    if not panel or panel.guild_id != guild_id:
        raise HTTPException(status_code=404, detail="Panel not found")

    # Check for duplicate name (excluding current panel)
    if name != panel.name:
        existing = await service.get_by_name(guild_id=guild_id, name=name)
        if existing:
            raise HTTPException(status_code=400, detail=f"Panel '{name}' already exists")

    # Parse JSON fields
    try:
        mappings = json.loads(role_mappings)
        req_roles = json.loads(required_roles)
        embed_cfg = json.loads(embed_config) if embed_config else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data") from None

    # Update panel
    try:
        channel_id_int = int(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid channel ID") from None

    panel.name = name
    panel.channel_id = channel_id_int
    panel.panel_type = panel_type
    panel.role_mappings = mappings
    panel.required_roles = req_roles
    panel.embed_config = embed_cfg if embed_cfg else None
    panel.dm_on_missing_role = dm_on_missing_role
    panel.dm_on_role_change = dm_on_role_change
    panel.exclusive_require_existing = exclusive_require_existing

    await session.commit()
    logger.info(f"[{guild_name}] Panel {panel.name} updated via web dashboard")

    # Return updated list
    return await list_panels(request=request, guild_id=guild_id, user=user, session=session)


@router.post("/{guild_id}/panels/{panel_id}/delete", response_class=HTMLResponse)
async def delete_panel(
    request: Request,
    guild_id: int,
    panel_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Delete a panel.

    Args:
        request: FastAPI request
        guild_id: Guild ID
        panel_id: Panel ID
        user: User with verified access
        session: Database session

    Returns:
        HTMLResponse: Updated panels list
    """
    discord_guild, _, _, _ = _get_guild_data(request=request, guild_id=guild_id)
    guild_name = discord_guild.name if discord_guild else "Unknown"

    service = ReactionRolesService(session)
    panel = await service.get_by_id(panel_id)

    if not panel or panel.guild_id != guild_id:
        raise HTTPException(status_code=404, detail="Panel not found")

    # Delete the Discord message if posted
    if panel.message_id and discord_guild:
        channel = discord_guild.get_channel(panel.channel_id)
        if channel:
            try:
                message = await channel.fetch_message(panel.message_id)
                await message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass  # Message already deleted or no permission

    await service.delete(panel_id=panel_id, guild_name=guild_name)
    await session.commit()

    # Return updated list
    return await list_panels(request=request, guild_id=guild_id, user=user, session=session)


@router.post("/{guild_id}/panels/{panel_id}/post", response_class=HTMLResponse)
async def post_panel(
    request: Request,
    guild_id: int,
    panel_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Post a panel to its channel.

    Args:
        request: FastAPI request
        guild_id: Guild ID
        panel_id: Panel ID
        user: User with verified access
        session: Database session

    Returns:
        HTMLResponse: Updated panels list
    """
    from discord_bot.roles.formatters import build_panel_embed

    discord_guild, _, _, _ = _get_guild_data(request=request, guild_id=guild_id)
    guild_name = discord_guild.name if discord_guild else "Unknown"

    if not discord_guild:
        raise HTTPException(status_code=400, detail="Guild not found")

    service = ReactionRolesService(session)
    panel = await service.get_by_id(panel_id)

    if not panel or panel.guild_id != guild_id:
        raise HTTPException(status_code=404, detail="Panel not found")

    if panel.message_id:
        raise HTTPException(status_code=400, detail="Panel is already posted")

    if not panel.role_mappings:
        raise HTTPException(status_code=400, detail="Add at least one role mapping before posting")

    channel = discord_guild.get_channel(panel.channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise HTTPException(status_code=400, detail="Channel not found")

    # Build and send embed
    embed = build_panel_embed(panel=panel, guild=discord_guild)

    try:
        message = await channel.send(embed=embed)

        # Add reactions
        for mapping in panel.role_mappings:
            emoji_str = mapping.get("emoji")
            if not emoji_str:
                continue
            emoji_id_raw = mapping.get("emoji_id")
            emoji: discord.PartialEmoji | str
            if emoji_id_raw:
                emoji = discord.PartialEmoji(name=emoji_str, id=int(emoji_id_raw))
            else:
                emoji = emoji_str
            if emoji:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass

        # Update panel with message ID
        await service.set_message_id(
            panel_id=panel.id, message_id=message.id, guild_name=guild_name
        )
        await session.commit()

    except discord.Forbidden:
        raise HTTPException(status_code=400, detail="Cannot send message to channel") from None

    # Return updated list
    return await list_panels(request=request, guild_id=guild_id, user=user, session=session)


@router.post("/{guild_id}/panels/{panel_id}/unpost", response_class=HTMLResponse)
async def unpost_panel(
    request: Request,
    guild_id: int,
    panel_id: int,
    user: GuildAccess,
    session: DbSession,
) -> HTMLResponse:
    """Remove a panel from its channel (unpost).

    Args:
        request: FastAPI request
        guild_id: Guild ID
        panel_id: Panel ID
        user: User with verified access
        session: Database session

    Returns:
        HTMLResponse: Updated panels list
    """
    discord_guild, _, _, _ = _get_guild_data(request=request, guild_id=guild_id)
    guild_name = discord_guild.name if discord_guild else "Unknown"

    service = ReactionRolesService(session)
    panel = await service.get_by_id(panel_id)

    if not panel or panel.guild_id != guild_id:
        raise HTTPException(status_code=404, detail="Panel not found")

    if not panel.message_id:
        raise HTTPException(status_code=400, detail="Panel is not posted")

    # Delete the Discord message
    if discord_guild:
        channel = discord_guild.get_channel(panel.channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(panel.message_id)
                await message.delete()
            except discord.NotFound:
                pass  # Message already deleted
            except discord.Forbidden:
                logger.warning(f"[{guild_name}] Cannot delete panel message - missing permissions")

    # Clear the message ID
    await service.set_message_id(panel_id=panel.id, message_id=None, guild_name=guild_name)
    await session.commit()

    logger.info(f"[{guild_name}] Panel {panel.name} unposted via web dashboard")

    # Return updated list
    return await list_panels(request=request, guild_id=guild_id, user=user, session=session)
