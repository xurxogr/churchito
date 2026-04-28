"""Pure functions for nickname calculation."""

import re
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=32)
def build_tag_pattern(tag_format: str) -> re.Pattern[str]:
    """Build regex to detect tags in the configured format.

    Converts "[ABC | {tag}]" into a pattern that matches "[ABC | CAP]", etc.

    Args:
        tag_format (str): Tag format (e.g.: "[ABC | {tag}]")

    Returns:
        re.Pattern[str]: Compiled regex pattern
    """
    # Escape special regex characters
    escaped = re.escape(tag_format)
    # Replace the escaped {tag} placeholder with pattern for any value
    tag_pattern = escaped.replace(r"\{tag\}", r"[^\]]+")
    # Full pattern: optional prefix (1-5 chars, no space) + tag + space + name
    full_pattern = rf"^(?:[^\[\]]{{1,5}})?{tag_pattern}\s+(.+)$"
    return re.compile(full_pattern)


# Generic fallback pattern for tags with structure [SOMETHING | SOMETHING]
# Used when format changes to clean tags from previous format
# The prefix (1-5 chars, no space) is only removed if followed by a bracketed tag
GENERIC_TAG_RE = re.compile(r"^(?:(?:[^\[\]]{1,5})?\[[^\]]+\]\s+)?(.+)$")


def extract_base_name(
    display_name: str,
    tag_format: str,
    known_prefixes: list[str] | None = None,
) -> str:
    """Extract base name by removing tag and/or prefix if they match.

    First tries to match the configured format.
    If no match, uses a generic pattern as fallback (for format changes).
    Finally, tries to remove known prefixes if there's no tag.

    Args:
        display_name (str): Current display name
        tag_format (str): Tag format (e.g.: "[ABC | {tag}]")
        known_prefixes (list[str] | None): List of known prefixes to remove

    Returns:
        str: Base name without tags or prefixes
    """
    name = display_name.strip()

    # Try with configured format
    pattern = build_tag_pattern(tag_format)
    match = pattern.match(name)
    if match:
        return match.group(1).strip()

    # Fallback: generic pattern to clean tags from previous format
    match = GENERIC_TAG_RE.match(name)
    if match:
        extracted = match.group(1).strip()
        # If fallback extracted something different, use it
        if extracted != name:
            return extracted

    # Remove known prefix if there's no tag (e.g.: "★ Xurxo" -> "Xurxo")
    if known_prefixes:
        for prefix in known_prefixes:
            if prefix and name.startswith(prefix + " "):
                return name[len(prefix) + 1 :].strip()

    return name


def find_matching_value(
    member_role_ids: list[int],
    roles_config: list[dict[str, Any]],
    value_key: str,
) -> str | None:
    """Find the first value that matches a member's role.

    The roles_config list is ordered by priority (first match wins).

    Args:
        member_role_ids (list[int]): Member's role IDs
        roles_config (list[dict[str, Any]]): List of {"role_id": int|str, value_key: str}
        value_key (str): Key of the value to extract (e.g.: "tag" or "prefix")

    Returns:
        str | None: Value of first matching role or None
    """
    member_role_set = set(member_role_ids)
    for role_config in roles_config:
        role_id = role_config.get("role_id")
        if role_id:
            # Handle both string and int role_ids (web form saves as string)
            try:
                role_id_int = int(role_id)
                if role_id_int in member_role_set:
                    value = role_config.get(value_key, "")
                    return str(value) if value else ""
            except (ValueError, TypeError):
                continue
    return None


def build_nickname(
    base_name: str,
    tag: str,
    prefix: str,
    tag_format: str,
) -> str:
    """Build complete nickname with prefix, tag and name.

    Args:
        base_name (str): User's base name
        tag (str): Tag to insert (e.g.: "CAP")
        prefix (str): Unicode prefix (e.g.: "★")
        tag_format (str): Tag format (e.g.: "[ABC | {tag}]")

    Returns:
        str: Complete nickname, truncated to 32 characters if necessary
    """
    # Only format the tag if there's an actual tag value
    # If only prefix exists without tag, don't include the empty tag format
    formatted_tag = tag_format.format(tag=tag) if tag else ""

    # Build nickname: prefix attaches directly (no extra space)
    # If user wants space, include it in prefix: "★ " instead of "★"
    if prefix and formatted_tag:
        prefix_part = f"{prefix}{formatted_tag}"
        nickname = f"{prefix_part} {base_name}"
    elif prefix:
        prefix_part = prefix
        nickname = f"{prefix_part} {base_name}"
    elif formatted_tag:
        prefix_part = formatted_tag
        nickname = f"{prefix_part} {base_name}"
    else:
        prefix_part = ""
        nickname = base_name

    # Truncate to 32 characters (Discord limit)
    if len(nickname) > 32:
        if prefix_part:
            # Calculate available space for base name
            available = 32 - len(prefix_part) - 1  # -1 for space
            if available > 0:
                nickname = f"{prefix_part} {base_name[:available]}"
            else:
                # Not enough space, use only truncated name
                nickname = base_name[:32]
        else:
            nickname = base_name[:32]

    return nickname


def compute_nickname(
    display_name: str,
    current_nick: str | None,
    member_role_ids: list[int],
    tags_config: list[dict[str, Any]],
    prefixes_config: list[dict[str, Any]],
    tag_format: str,
) -> str | None:
    """Calculate the new nickname for a member.

    Args:
        display_name (str): Current display name (nick or username)
        current_nick (str | None): Member's current nick (can be None)
        member_role_ids (list[int]): Member's role IDs
        tags_config (list[dict[str, Any]]): List of {"role_id": int, "tag": str}
        prefixes_config (list[dict[str, Any]]): List of {"role_id": int, "prefix": str}
        tag_format (str): Tag format (e.g.: "[ABC | {tag}]")

    Returns:
        str | None: New nickname or None if no change needed
    """
    # Extract known prefixes from config
    known_prefixes = [cfg.get("prefix", "") for cfg in prefixes_config if cfg.get("prefix")]

    # Extract base name using configured format and known prefixes
    base_name = extract_base_name(
        display_name=display_name, tag_format=tag_format, known_prefixes=known_prefixes
    )

    # Find matching tag and prefix (independent)
    tag = find_matching_value(
        member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
    )
    prefix = find_matching_value(
        member_role_ids=member_role_ids, roles_config=prefixes_config, value_key="prefix"
    )

    # If there's neither tag nor prefix, clean nickname if it had something
    if tag is None and prefix is None:
        if base_name != display_name and base_name != current_nick:
            return base_name
        return None

    # Build new nickname
    new_nickname = build_nickname(
        base_name=base_name, tag=tag or "", prefix=prefix or "", tag_format=tag_format
    )

    # Check if there's a change
    if new_nickname == current_nick or new_nickname == display_name:
        return None

    return new_nickname
