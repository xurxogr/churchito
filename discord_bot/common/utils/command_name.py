"""Helpers for user-configurable slash command names.

Discord only registers command names made of lowercase letters, digits,
hyphens and underscores (1-32 characters); discord.py enforces the same
rule when the command object is created. These helpers apply that rule at
save time (dashboard) and at registration time (cogs), so a bad name is
rejected with a clear message instead of silently breaking registration.
"""

import logging
import unicodedata
from typing import Any

import discord
from discord import app_commands
from discord.app_commands.commands import validate_name

logger = logging.getLogger(__name__)

COMMAND_NAME_HINT = (
    "Command names must be 1-32 characters of lowercase letters, numbers, hyphens or "
    "underscores, without spaces or a leading slash"
)


def normalize_command_name(value: str) -> str:
    """Compose Unicode (NFC) and strip surrounding whitespace.

    Accented letters typed or pasted in decomposed form (``n`` + combining
    tilde) are composed so Discord sees a single letter.

    Args:
        value (str): Raw command name.

    Returns:
        str: Normalized command name.
    """
    return unicodedata.normalize("NFC", value).strip()


def validate_command_name(value: Any) -> str | None:
    """Validate a configured slash command name.

    An empty value is accepted and means "use the default name".

    Args:
        value (Any): Value entered in the dashboard.

    Returns:
        str | None: Error message, or None when the name is acceptable.
    """
    if not isinstance(value, str):
        return COMMAND_NAME_HINT
    name = normalize_command_name(value)
    if not name:
        return None
    try:
        validate_name(name)
    except ValueError:
        return f"'{value}' is not a valid command name. {COMMAND_NAME_HINT}"
    return None


def resolve_command_name(*, configured: Any, default: str, guild_name: str) -> str:
    """Pick the command name to register for a guild.

    Args:
        configured (Any): Value stored in the guild configuration.
        default (str): Name to use when nothing valid is configured.
        guild_name (str): Guild name for log context.

    Returns:
        str: Normalized configured name, or ``default`` when it is empty or invalid.
    """
    if not isinstance(configured, str) or not normalize_command_name(configured):
        return default
    error = validate_command_name(configured)
    if error is not None:
        logger.warning(
            f"[{guild_name}] Configured command name '{configured}' rejected "
            f"({COMMAND_NAME_HINT}); registering '/{default}' instead"
        )
        return default
    return normalize_command_name(configured)


def _is_name_free(
    *,
    tree: app_commands.CommandTree[Any],
    guild: discord.Guild,
    name: str,
    current: str | None,
) -> bool:
    """Whether ``name`` can be registered in ``guild`` (unused, or held by this command).

    Args:
        tree (app_commands.CommandTree[Any]): Bot command tree.
        guild (discord.Guild): Guild the command is registered in.
        name (str): Candidate command name.
        current (str | None): Name this command currently holds in the guild, if any.

    Returns:
        bool: True when nothing else in the guild uses ``name``.
    """
    return name == current or tree.get_command(name, guild=guild) is None


def choose_command_name(
    *,
    tree: app_commands.CommandTree[Any],
    guild: discord.Guild,
    configured: Any,
    default: str,
    current: str | None = None,
) -> str | None:
    """Pick a registrable name: valid, and not used by another command in the guild.

    Invalid or colliding configured names fall back to ``default`` with a
    warning; when the default is taken as well, an error is logged and None
    is returned so the caller leaves the guild's commands untouched.

    Args:
        tree (app_commands.CommandTree[Any]): Bot command tree.
        guild (discord.Guild): Guild the command is registered in.
        configured (Any): Value stored in the guild configuration.
        default (str): Fallback command name.
        current (str | None): Name this command currently holds in the guild, if any.

    Returns:
        str | None: Name to register, or None when neither candidate is available.
    """
    name = resolve_command_name(configured=configured, default=default, guild_name=guild.name)
    if _is_name_free(tree=tree, guild=guild, name=name, current=current):
        return name
    if name != default:
        logger.warning(
            f"[{guild.name}] Command name '/{name}' is already used by another command; "
            f"registering '/{default}' instead"
        )
        if _is_name_free(tree=tree, guild=guild, name=default, current=current):
            return default
    logger.error(
        f"[{guild.name}] Cannot register '/{default}': the name is already used by "
        f"another command in this guild"
    )
    return None
