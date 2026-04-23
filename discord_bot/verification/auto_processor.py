"""Automatic verification processor."""

import logging
from typing import Any

from discord_bot.verification.enums import (
    ConfigKey,
    NameMatchMode,
    RejectType,
    VerificationType,
)
from discord_bot.verification.formatters import format_message
from discord_bot.verification.models import VerificationAPIResponse, VerificationRequest

logger = logging.getLogger(__name__)


def calculate_time_diff_days(ingame_time: str, current_ingame_time: str) -> int:
    """Calculate difference in days between in-game times.

    Args:
        ingame_time (str): Player time (format "268, 07:41").
        current_ingame_time (str): Current game time (format "278, 08:34").

    Returns:
        int: Absolute difference in days.
    """
    try:
        # Extract days (number before the comma)
        ingame_days = int(ingame_time.split(",")[0].strip())
        current_days = int(current_ingame_time.split(",")[0].strip())
        return abs(current_days - ingame_days)
    except (ValueError, IndexError) as e:
        logger.warning(
            f"Error parsing time difference: {ingame_time} vs {current_ingame_time}: {e}"
        )
        return 0


def names_match(discord_name: str, game_name: str, mode: NameMatchMode) -> bool:
    """Check if Discord name matches the game name.

    Args:
        discord_name (str): Discord display name.
        game_name (str): In-game name from the API.
        mode (NameMatchMode): Comparison mode (EXACT or CONTAINS).

    Returns:
        bool: True if names match according to the mode.
    """
    discord_lower = discord_name.lower().strip()
    game_lower = game_name.lower().strip()

    if mode == NameMatchMode.EXACT:
        return discord_lower == game_lower
    elif mode == NameMatchMode.CONTAINS:
        return discord_lower in game_lower or game_lower in discord_lower
    return True


def is_auto_reject_enabled(config: dict[str, Any], reason: RejectType) -> bool:
    """Check if auto-rejection is enabled for a specific reason.

    Args:
        config (dict[str, Any]): Cog configuration.
        reason (RejectType): The rejection reason type.

    Returns:
        bool: True if auto-rejection is enabled for this reason.
    """
    config_key = get_auto_reject_config_key(reason)
    if not config_key:
        return True  # Default to enabled for unknown reasons

    # Default to True if not configured
    return bool(config.get(config_key, True))


def get_auto_reject_config_key(reason: RejectType) -> ConfigKey | None:
    """Get the config key for an auto-reject toggle.

    Args:
        reason (RejectType): The rejection reason type.

    Returns:
        ConfigKey | None: The config key for the toggle, or None if unknown.
    """
    config_key_map = {
        RejectType.INVALID_SCREENSHOTS: ConfigKey.AUTO_REJECT_INVALID_SCREENSHOTS,
        RejectType.NAME_MISMATCH: ConfigKey.AUTO_REJECT_NAME_MISMATCH,
        RejectType.HAS_REGIMENT: ConfigKey.AUTO_REJECT_HAS_REGIMENT,
        RejectType.TIME_DIFF: ConfigKey.AUTO_REJECT_TIME_DIFF,
        RejectType.WRONG_SHARD: ConfigKey.AUTO_REJECT_WRONG_SHARD,
        RejectType.WRONG_FACTION: ConfigKey.AUTO_REJECT_WRONG_FACTION,
    }
    return config_key_map.get(reason)


def get_rejection_message(
    config: dict[str, Any],
    reason: RejectType,
    **format_kwargs: Any,
) -> str:
    """Get the rejection message for a rejection type.

    Args:
        config (dict[str, Any]): Cog configuration.
        reason (RejectType): The rejection reason type.
        **format_kwargs: Placeholders for message formatting (e.g., shard="ABLE").

    Returns:
        str: The formatted rejection message.
    """
    message_key_map = {
        RejectType.INVALID_SCREENSHOTS: ConfigKey.REJECT_WRONG_CAPTURES,
        RejectType.NAME_MISMATCH: ConfigKey.REJECT_NAME_MISMATCH,
        RejectType.HAS_REGIMENT: ConfigKey.REJECT_HAS_REGIMENT,
        RejectType.TIME_DIFF: ConfigKey.REJECT_TIME_DIFF,
        RejectType.WRONG_SHARD: ConfigKey.REJECT_WRONG_SHARD,
        RejectType.WRONG_FACTION: ConfigKey.REJECT_WRONG_FACTION,
    }
    default_messages = {
        RejectType.INVALID_SCREENSHOTS: "Screenshots incorrect or unreadable",
        RejectType.NAME_MISMATCH: "Username does not match",
        RejectType.HAS_REGIMENT: "User already belongs to a regiment",
        RejectType.TIME_DIFF: "Screenshot too old",
        RejectType.WRONG_SHARD: "Wrong shard, must be {shard}",
        RejectType.WRONG_FACTION: "Wrong faction",
    }

    message_key = message_key_map.get(reason)
    default = default_messages.get(reason, "Verification rejected")
    template = config.get(message_key, default) if message_key else default

    if format_kwargs:
        return format_message(template, **format_kwargs)
    return template


def extract_regiment_id(regiment: str) -> str | None:
    """Extract the regiment ID from the full format.

    Expected format is: [ID#number] Regiment Name
    For example: [7-HP#8707] 7th Hispanic Platoon -> 7-HP#8707

    Args:
        regiment (str): Full regiment string.

    Returns:
        str | None: The regiment ID (content between brackets) or None.
    """
    if not regiment:
        return None

    # Find the content between brackets
    if not regiment.startswith("["):
        return None

    bracket_end = regiment.find("]")
    if bracket_end == -1:
        return None

    return regiment[1:bracket_end]


def extract_regiment_number(regiment_id: str) -> str | None:
    """Extract the numeric part after # from a regiment ID.

    This is used for comparison since OCR may miss characters like hyphens.
    For example: 7-HP#8707 -> 8707, 7HP#8707 -> 8707

    Args:
        regiment_id (str): Regiment ID (e.g., "7-HP#8707").

    Returns:
        str | None: The numeric part after # or None if not found.
    """
    if not regiment_id or "#" not in regiment_id:
        return None

    return regiment_id.split("#")[-1]


def process_verification(
    request: VerificationRequest,
    api_response: VerificationAPIResponse,
    config: dict[str, Any],
    member_display_name: str,
) -> RejectType | None:
    """Process verification rules and determine approval/rejection.

    Check order: Faction -> Shard -> Regiment -> Name -> Time diff
    (Invalid screenshots is handled separately before this function is called)

    Args:
        request (VerificationRequest): Verification request.
        api_response (VerificationAPIResponse): API response with player data.
        config (dict[str, Any]): Cog configuration.
        member_display_name (str): Discord member display name.

    Returns:
        RejectType | None: The rejection reason if rejected, None if approved.
            Use get_rejection_message() to get the user-facing message.
    """
    # 1. Check faction (if configured)
    expected_faction = config.get(ConfigKey.VERIFICATION_FACTION)
    if expected_faction and api_response.faction.lower() != expected_faction.lower():
        return RejectType.WRONG_FACTION

    # 2. Check shard (if configured)
    expected_shard = config.get(ConfigKey.VERIFICATION_SHARD)
    if expected_shard and api_response.shard.upper() != expected_shard.upper():
        return RejectType.WRONG_SHARD

    # 3. Check regiment (only for REGULAR verification)
    if request.verification_type == VerificationType.REGULAR and api_response.regiment:
        valid_regiment = config.get(ConfigKey.VERIFICATION_VALID_REGIMENT, "")
        logger.debug(
            f"Regiment check: api_regiment={api_response.regiment!r}, "
            f"valid_regiment={valid_regiment!r}, type={type(valid_regiment)}"
        )
        if valid_regiment:
            # If a valid regiment is configured, only reject if it doesn't match
            # Compare only the #<number> part to handle OCR errors in prefix
            detected_regiment_id = extract_regiment_id(api_response.regiment)
            detected_number = extract_regiment_number(detected_regiment_id or "")
            valid_number = extract_regiment_number(valid_regiment)
            logger.debug(
                f"Regiment comparison: detected_id={detected_regiment_id!r}, "
                f"detected_number={detected_number!r}, valid_number={valid_number!r}, "
                f"match={detected_number == valid_number}"
            )
            if detected_number != valid_number:
                return RejectType.HAS_REGIMENT
        else:
            # If no valid regiment is configured, reject any regiment
            logger.debug("No valid_regiment configured, rejecting any regiment")
            return RejectType.HAS_REGIMENT

    # 4. Check name match (if enabled)
    match_name_mode = config.get(ConfigKey.VERIFICATION_MATCH_NAME, NameMatchMode.NONE)
    # Handle legacy boolean values for compatibility
    if match_name_mode is True:
        match_name_mode = NameMatchMode.EXACT
    elif match_name_mode is False or not match_name_mode:
        match_name_mode = NameMatchMode.NONE

    if match_name_mode != NameMatchMode.NONE:
        if not names_match(
            discord_name=member_display_name,
            game_name=api_response.name,
            mode=match_name_mode,
        ):
            return RejectType.NAME_MISMATCH

    # 5. Check time difference (if configured > 0)
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    if time_diff_limit and time_diff_limit > 0:
        diff = calculate_time_diff_days(
            ingame_time=api_response.ingame_time,
            current_ingame_time=api_response.current_ingame_time,
        )
        if diff > time_diff_limit:
            return RejectType.TIME_DIFF

    # All checks passed
    return None
