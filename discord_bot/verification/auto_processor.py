"""Procesador automático de verificaciones."""

import logging
from typing import Any

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.enums import ConfigKey, NameMatchMode, VerificationType
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
        # Extraer días (número antes de la coma)
        ingame_days = int(ingame_time.split(",")[0].strip())
        current_days = int(current_ingame_time.split(",")[0].strip())
        return abs(current_days - ingame_days)
    except (ValueError, IndexError) as e:
        logger.warning(
            f"Error parseando diferencia de tiempo: {ingame_time} vs {current_ingame_time}: {e}"
        )
        return 0


def names_match(discord_name: str, game_name: str, mode: NameMatchMode) -> bool:
    """Comprobar si el nombre de Discord coincide con el nombre del juego.

    Args:
        discord_name: Nombre de display de Discord
        game_name: Nombre en el juego desde la API
        mode: Modo de comparación (EXACT o CONTAINS)

    Returns:
        True si los nombres coinciden según el modo
    """
    discord_lower = discord_name.lower().strip()
    game_lower = game_name.lower().strip()

    if mode == NameMatchMode.EXACT:
        return discord_lower == game_lower
    elif mode == NameMatchMode.CONTAINS:
        return discord_lower in game_lower or game_lower in discord_lower
    return True


def process_verification(
    request: VerificationRequest,
    api_response: VerificationAPIResponse,
    config: dict[str, Any],
    member_display_name: str,
) -> tuple[bool, str | None]:
    """Procesar reglas de verificación y determinar aprobación/rechazo.

    Args:
        request: Solicitud de verificación
        api_response: Respuesta de la API con datos del jugador
        config: Configuración del cog
        member_display_name: Nombre de display del miembro en Discord

    Returns:
        Tupla de (debe_aprobar, motivo_rechazo)
    """
    # 1. Comprobar coincidencia de nombre (si está habilitado)
    match_name_mode = config.get(ConfigKey.VERIFICATION_MATCH_NAME, NameMatchMode.NONE)
    # Manejar valores booleanos legacy para compatibilidad
    if match_name_mode is True:
        match_name_mode = NameMatchMode.EXACT
    elif match_name_mode is False or not match_name_mode:
        match_name_mode = NameMatchMode.NONE

    if match_name_mode != NameMatchMode.NONE:
        if not names_match(member_display_name, api_response.name, match_name_mode):
            reason = config.get(ConfigKey.REJECT_NAME_MISMATCH) or "Nombre de usuario no coincide"
            return False, reason

    # 2. Comprobar regimiento (solo para verificación REGULAR - rechazar si tiene regimiento)
    if request.verification_type == VerificationType.REGULAR and api_response.regiment:
        reason = (
            config.get(ConfigKey.REJECT_HAS_REGIMENT) or "El usuario ya pertenece a un regimiento"
        )
        return False, reason

    # 3. Comprobar diferencia de tiempo (si está configurado > 0)
    time_diff_limit = config.get(ConfigKey.VERIFICATION_TIME_DIFF, 0)
    if time_diff_limit and time_diff_limit > 0:
        diff = calculate_time_diff_days(api_response.ingame_time, api_response.current_ingame_time)
        if diff > time_diff_limit:
            reason = config.get(ConfigKey.REJECT_TIME_DIFF) or "Captura demasiado antigua"
            return False, reason

    # 4. Comprobar shard (si está configurado)
    expected_shard = config.get(ConfigKey.VERIFICATION_SHARD)
    if expected_shard and api_response.shard.upper() != expected_shard.upper():
        reason_template = (
            config.get(ConfigKey.REJECT_WRONG_SHARD) or "Shard incorrecto, debe ser {shard}"
        )
        reason = format_message(reason_template, shard=expected_shard)
        return False, reason

    # 5. Comprobar facción (si está configurado)
    expected_faction = config.get(ConfigKey.VERIFICATION_FACTION)
    if expected_faction and api_response.faction.lower() != expected_faction.lower():
        reason = config.get(ConfigKey.REJECT_WRONG_FACTION) or "Facción incorrecta"
        return False, reason

    # Todas las comprobaciones pasaron
    return True, None
