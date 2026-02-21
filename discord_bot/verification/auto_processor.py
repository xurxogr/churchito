"""Procesador automático de verificaciones."""

import logging
from typing import Any

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import format_message
from discord_bot.verification.models import VerificationRequest

logger = logging.getLogger(__name__)


def calculate_time_diff_days(ingame_time: str, current_ingame_time: str) -> int:
    """Calcular diferencia de días entre tiempos de juego.

    Args:
        ingame_time: Tiempo del jugador (formato "268, 07:41")
        current_ingame_time: Tiempo actual del juego (formato "278, 08:34")

    Returns:
        Diferencia absoluta en días
    """
    try:
        # Extract days (number before comma)
        ingame_days = int(ingame_time.split(",")[0].strip())
        current_days = int(current_ingame_time.split(",")[0].strip())
        return abs(current_days - ingame_days)
    except (ValueError, IndexError) as e:
        logger.warning(f"Error parsing time diff: {ingame_time} vs {current_ingame_time}: {e}")
        return 0


def names_match(discord_name: str, game_name: str) -> bool:
    """Check if Discord name matches game name (case-insensitive).

    Args:
        discord_name: Discord display name
        game_name: In-game name from API

    Returns:
        True if names match
    """
    return discord_name.lower().strip() == game_name.lower().strip()


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
    match_name = config.get(ConfigKey.VERIFICATION_MATCH_NAME, False)
    if match_name and not names_match(member_display_name, api_response.name):
        reason = config.get(ConfigKey.REJECT_NAME_MISMATCH) or "Nombre de usuario no coincide"
        return False, reason

    # 2. Check regiment (only for REGULAR verification - reject if has regiment)
    if request.verification_type == VerificationType.REGULAR and api_response.regiment:
        reason = (
            config.get(ConfigKey.REJECT_HAS_REGIMENT) or "El usuario ya pertenece a un regimiento"
        )
        return False, reason

    # 3. Check time diff (if configured > 0)
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    if time_diff_limit and time_diff_limit > 0:
        diff = calculate_time_diff_days(api_response.ingame_time, api_response.current_ingame_time)
        if diff > time_diff_limit:
            reason = config.get(ConfigKey.REJECT_TIME_DIFF) or "Captura demasiado antigua"
            return False, reason

    # 4. Check shard (if configured)
    expected_shard = config.get(ConfigKey.VERIFICATION_SHARD)
    if expected_shard and api_response.shard.upper() != expected_shard.upper():
        reason_template = (
            config.get(ConfigKey.REJECT_WRONG_SHARD) or "Shard incorrecto, debe ser {shard}"
        )
        reason = format_message(reason_template, shard=expected_shard)
        return False, reason

    # 5. Check faction (if configured)
    expected_faction = config.get(ConfigKey.VERIFICATION_FACTION)
    if expected_faction and api_response.faction.lower() != expected_faction.lower():
        reason = config.get(ConfigKey.REJECT_WRONG_FACTION) or "Facción incorrecta"
        return False, reason

    # All checks passed
    return True, None
