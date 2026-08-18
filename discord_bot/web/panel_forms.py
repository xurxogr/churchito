"""Validation helpers for the reaction panel dashboard forms."""

import json
from typing import Any

from fastapi import HTTPException

from discord_bot.roles.models import PanelType

# Matches the ReactionPanel.name column length
MAX_PANEL_NAME_LENGTH = 100
# Discord allows this many distinct reactions on a message, and every
# mapping needs its own reaction to be usable
MAX_ROLE_MAPPINGS = 20


def validate_panel_fields(name: str, panel_type: str) -> None:
    """Validate the user-editable panel name and type.

    Args:
        name (str): Panel name from the form.
        panel_type (str): Panel type from the form.

    Raises:
        HTTPException: 400 if the name is empty or too long, or the type is unknown.
    """
    if not name or len(name) > MAX_PANEL_NAME_LENGTH:
        raise HTTPException(status_code=400, detail="Invalid panel name")

    if panel_type not in [t.value for t in PanelType]:
        raise HTTPException(status_code=400, detail="Invalid panel type")


def parse_snowflake(value: Any) -> int:
    """Coerce a decoded JSON value into a Discord snowflake ID.

    The dashboard sends snowflakes as strings to keep their full 64-bit
    precision in JavaScript, so both integers and digit strings are accepted.

    Args:
        value (Any): Decoded JSON value.

    Returns:
        int: The ID as an integer.

    Raises:
        ValueError: If the value is not an integer or a digit string.
    """
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"invalid ID: {value!r}")
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"invalid ID: {value!r}") from None


def parse_required_roles(value: Any) -> list[int]:
    """Coerce the decoded ``required_roles`` payload into a list of role IDs.

    Args:
        value (Any): Decoded JSON value from the form.

    Returns:
        list[int]: Role IDs as integers.

    Raises:
        ValueError: If the value is not a list of integer or digit-string IDs.
    """
    if not isinstance(value, list):
        raise ValueError("required roles must be a list")
    return [parse_snowflake(item) for item in value]


def parse_role_mapping(item: Any) -> dict[str, Any]:
    """Validate and normalize a single emoji-role mapping from the form.

    Only the known keys are kept, IDs are stored as integers (matching the
    mappings created from slash commands) and text fields are stripped.

    Args:
        item (Any): Decoded JSON value for one mapping.

    Returns:
        dict[str, Any]: Mapping with ``emoji``, ``role_id`` and optional
            ``emoji_id`` / ``display_name``.

    Raises:
        ValueError: If the mapping is not an object with an emoji and a valid role ID.
    """
    if not isinstance(item, dict):
        raise ValueError("each mapping must be an object")

    emoji = item.get("emoji")
    if not isinstance(emoji, str) or not emoji.strip():
        raise ValueError("mapping emoji is required")
    if "role_id" not in item:
        raise ValueError("mapping role_id is required")

    mapping: dict[str, Any] = {"emoji": emoji.strip(), "role_id": parse_snowflake(item["role_id"])}

    emoji_id = item.get("emoji_id")
    if emoji_id not in (None, ""):
        mapping["emoji_id"] = parse_snowflake(emoji_id)

    display_name = item.get("display_name")
    if display_name not in (None, ""):
        if not isinstance(display_name, str):
            raise ValueError("mapping display_name must be text")
        if display_name.strip():
            mapping["display_name"] = display_name.strip()

    return mapping


def parse_role_mappings(value: Any) -> list[dict[str, Any]]:
    """Coerce the decoded ``role_mappings`` payload into normalized mappings.

    Args:
        value (Any): Decoded JSON value from the form.

    Returns:
        list[dict[str, Any]]: Normalized mappings.

    Raises:
        ValueError: If the value is not a list of valid mappings, has more
            mappings than reactions fit on a message, or repeats an emoji.
    """
    if not isinstance(value, list):
        raise ValueError("role mappings must be a list")
    if len(value) > MAX_ROLE_MAPPINGS:
        raise ValueError(f"at most {MAX_ROLE_MAPPINGS} mappings are allowed")

    mappings = [parse_role_mapping(item) for item in value]

    # Reactions are looked up by emoji, so a repeated one would never reach
    # its second role (the slash command rejects this too)
    seen: set[int | str] = set()
    for mapping in mappings:
        emoji_key: int | str = mapping.get("emoji_id") or mapping["emoji"]
        if emoji_key in seen:
            raise ValueError(f"duplicate emoji: {mapping['emoji']}")
        seen.add(emoji_key)
    return mappings


def parse_panel_json_fields(
    role_mappings: str,
    embed_config: str,
    required_roles: str = "[]",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[int]]:
    """Decode and validate the JSON-encoded panel form fields.

    Args:
        role_mappings (str): JSON list of emoji-role mappings.
        embed_config (str): JSON object with the embed configuration.
        required_roles (str): JSON list of required role IDs. Defaults to "[]".

    Returns:
        tuple[list[dict[str, Any]], dict[str, Any], list[int]]: Normalized
            mappings, embed config and required role IDs.

    Raises:
        HTTPException: 400 if any field is not valid JSON or has the wrong shape.
    """
    try:
        raw_mappings = json.loads(role_mappings) if role_mappings else []
        raw_embed = json.loads(embed_config) if embed_config else {}
        raw_roles = json.loads(required_roles) if required_roles else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data") from None

    try:
        mappings = parse_role_mappings(raw_mappings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid role mappings: {e}") from None

    if not isinstance(raw_embed, dict):
        raise HTTPException(status_code=400, detail="Invalid embed config: must be an object")

    try:
        req_roles = parse_required_roles(raw_roles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid required roles: {e}") from None

    return mappings, raw_embed, req_roles
