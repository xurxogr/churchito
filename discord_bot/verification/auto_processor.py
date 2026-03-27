"""Automatic verification processor."""

import logging
from typing import Any

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.enums import ConfigKey, NameMatchMode, VerificationType
from discord_bot.verification.formatters import format_message
from discord_bot.verification.models import VerificationRequest

logger = logging.getLogger(__name__)


def calculate_time_diff_days(ingame_time: str, current_ingame_time: str) -> int:
    """Calculate difference in days between in-game times.

    Args:
        ingame_time: Player time (format "268, 07:41")
        current_ingame_time: Current game time (format "278, 08:34")

    Returns:
        Absolute difference in days
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
        discord_name: Discord display name
        game_name: In-game name from the API
        mode: Comparison mode (EXACT or CONTAINS)

    Returns:
        True if names match according to the mode
    """
    discord_lower = discord_name.lower().strip()
    game_lower = game_name.lower().strip()

    if mode == NameMatchMode.EXACT:
        return discord_lower == game_lower
    elif mode == NameMatchMode.CONTAINS:
        return discord_lower in game_lower or game_lower in discord_lower
    return True


def extract_regiment_id(regiment: str) -> str | None:
    """Extract the regiment ID from the full format.

    Expected format is: [ID#number] Regiment Name
    For example: [7-HP#8707] 7th Hispanic Platoon -> 7-HP#8707

    Args:
        regiment: Full regiment string

    Returns:
        The complete regiment ID (content between brackets) or None if cannot be extracted
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


def process_verification(
    request: VerificationRequest,
    api_response: VerificationAPIResponse,
    config: dict[str, Any],
    member_display_name: str,
) -> tuple[bool, str | None]:
    """Process verification rules and determine approval/rejection.

    Args:
        request: Verification request
        api_response: API response with player data
        config: Cog configuration
        member_display_name: Discord member display name

    Returns:
        Tuple of (should_approve, rejection_reason)
    """
    # 1. Check name match (if enabled)
    match_name_mode = config.get(ConfigKey.VERIFICATION_MATCH_NAME, NameMatchMode.NONE)
    # Handle legacy boolean values for compatibility
    if match_name_mode is True:
        match_name_mode = NameMatchMode.EXACT
    elif match_name_mode is False or not match_name_mode:
        match_name_mode = NameMatchMode.NONE

    if match_name_mode != NameMatchMode.NONE:
        if not names_match(member_display_name, api_response.name, match_name_mode):
            reason = config.get(ConfigKey.REJECT_NAME_MISMATCH) or "Username does not match"
            return False, reason

    # 2. Check regiment (only for REGULAR verification)
    if request.verification_type == VerificationType.REGULAR and api_response.regiment:
        valid_regiment = config.get(ConfigKey.VERIFICATION_VALID_REGIMENT, "")
        if valid_regiment:
            # If a valid regiment is configured, only reject if it doesn't match
            detected_regiment_id = extract_regiment_id(api_response.regiment)
            if detected_regiment_id != valid_regiment:
                reason = (
                    config.get(ConfigKey.REJECT_HAS_REGIMENT)
                    or "User already belongs to a regiment"
                )
                return False, reason
        else:
            # If no valid regiment is configured, reject any regiment
            reason = (
                config.get(ConfigKey.REJECT_HAS_REGIMENT) or "User already belongs to a regiment"
            )
            return False, reason

    # 3. Check time difference (if configured > 0)
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    if time_diff_limit and time_diff_limit > 0:
        diff = calculate_time_diff_days(api_response.ingame_time, api_response.current_ingame_time)
        if diff > time_diff_limit:
            reason = config.get(ConfigKey.REJECT_TIME_DIFF) or "Screenshot too old"
            return False, reason

    # 4. Check shard (if configured)
    expected_shard = config.get(ConfigKey.VERIFICATION_SHARD)
    if expected_shard and api_response.shard.upper() != expected_shard.upper():
        reason_template = config.get(ConfigKey.REJECT_WRONG_SHARD) or "Wrong shard, must be {shard}"
        reason = format_message(reason_template, shard=expected_shard)
        return False, reason

    # 5. Check faction (if configured)
    expected_faction = config.get(ConfigKey.VERIFICATION_FACTION)
    if expected_faction and api_response.faction.lower() != expected_faction.lower():
        reason = config.get(ConfigKey.REJECT_WRONG_FACTION) or "Wrong faction"
        return False, reason

    # All checks passed
    return True, None
