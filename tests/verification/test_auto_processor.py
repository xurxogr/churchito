"""Tests para discord_bot/verification/auto_processor.py."""

from typing import Any
from unittest.mock import MagicMock

from discord_bot.verification.api_client import VerificationAPIResponse
from discord_bot.verification.auto_processor import (
    calculate_time_diff_days,
    extract_regiment_id,
    names_match,
    process_verification,
)
from discord_bot.verification.enums import ConfigKey, NameMatchMode, VerificationType


class TestCalculateTimeDiffDays:
    """Tests para calculate_time_diff_days."""

    def test_same_day(self) -> None:
        """Probar cuando son el mismo día."""
        result = calculate_time_diff_days("268, 07:41", "268, 08:34")
        assert result == 0

    def test_ten_days_diff(self) -> None:
        """Probar diferencia de 10 días."""
        result = calculate_time_diff_days("268, 07:41", "278, 08:34")
        assert result == 10

    def test_negative_diff(self) -> None:
        """Probar que retorna valor absoluto."""
        result = calculate_time_diff_days("278, 07:41", "268, 08:34")
        assert result == 10

    def test_invalid_format(self) -> None:
        """Probar con formato inválido retorna 0."""
        result = calculate_time_diff_days("invalid", "278, 08:34")
        assert result == 0

    def test_empty_string(self) -> None:
        """Probar con string vacío retorna 0."""
        result = calculate_time_diff_days("", "278, 08:34")
        assert result == 0


class TestNamesMatch:
    """Tests para names_match."""

    def test_exact_match(self) -> None:
        """Probar match exacto."""
        assert names_match("Player", "Player", NameMatchMode.EXACT) is True

    def test_exact_case_insensitive(self) -> None:
        """Probar que es case insensitive en modo exacto."""
        assert names_match("PLAYER", "player", NameMatchMode.EXACT) is True
        assert names_match("Player", "PLAYER", NameMatchMode.EXACT) is True

    def test_exact_with_whitespace(self) -> None:
        """Probar que maneja espacios en modo exacto."""
        assert names_match("  Player  ", "Player", NameMatchMode.EXACT) is True

    def test_exact_different_names(self) -> None:
        """Probar nombres diferentes en modo exacto."""
        assert names_match("Player1", "Player2", NameMatchMode.EXACT) is False

    def test_contains_discord_in_game(self) -> None:
        """Probar que nombre de Discord está contenido en nombre del juego."""
        assert names_match("Player", "Player [TAG]", NameMatchMode.CONTAINS) is True

    def test_contains_game_in_discord(self) -> None:
        """Probar que nombre del juego está contenido en nombre de Discord."""
        assert names_match("[TAG] Player", "Player", NameMatchMode.CONTAINS) is True

    def test_contains_case_insensitive(self) -> None:
        """Probar que contains es case insensitive."""
        assert names_match("PLAYER", "player [tag]", NameMatchMode.CONTAINS) is True

    def test_contains_no_match(self) -> None:
        """Probar que contains falla cuando no hay coincidencia."""
        assert names_match("Player1", "Player2", NameMatchMode.CONTAINS) is False

    def test_none_mode_always_true(self) -> None:
        """Probar que modo NONE siempre retorna True."""
        assert names_match("Player1", "Player2", NameMatchMode.NONE) is True


class TestExtractRegimentId:
    """Tests para extract_regiment_id."""

    def test_standard_format(self) -> None:
        """Probar formato estándar [ID#número] Nombre."""
        result = extract_regiment_id("[7-HP#8707] 7th Hispanic Platoon")
        assert result == "7-HP#8707"

    def test_different_id_format(self) -> None:
        """Probar con otro formato de ID."""
        result = extract_regiment_id("[ABC#1234] Some Regiment Name")
        assert result == "ABC#1234"

    def test_no_hash(self) -> None:
        """Probar cuando no hay # en el contenido."""
        result = extract_regiment_id("[SOLO] Regiment Name")
        assert result == "SOLO"

    def test_empty_string(self) -> None:
        """Probar con string vacío."""
        result = extract_regiment_id("")
        assert result is None

    def test_no_brackets(self) -> None:
        """Probar cuando no hay corchetes."""
        result = extract_regiment_id("SomeRegiment")
        assert result is None

    def test_no_closing_bracket(self) -> None:
        """Probar cuando falta el corchete de cierre."""
        result = extract_regiment_id("[7-HP#8707 Missing bracket")
        assert result is None

    def test_empty_brackets(self) -> None:
        """Probar con corchetes vacíos."""
        result = extract_regiment_id("[] Regiment Name")
        assert result == ""

    def test_complex_id(self) -> None:
        """Probar con ID complejo."""
        result = extract_regiment_id("[82DK-TF#5555] 82nd Task Force")
        assert result == "82DK-TF#5555"


class TestProcessVerification:
    """Tests para process_verification."""

    def _create_request(
        self, verification_type: VerificationType = VerificationType.REGULAR
    ) -> MagicMock:
        """Crear un mock de VerificationRequest."""
        request = MagicMock()
        request.verification_type = verification_type
        return request

    def _create_api_response(
        self,
        name: str = "TestPlayer",
        regiment: str = "",
        faction: str = "colonial",
        shard: str = "ABLE",
        ingame_time: str = "268, 07:41",
        current_ingame_time: str = "268, 08:34",
    ) -> VerificationAPIResponse:
        """Crear una respuesta de API."""
        return VerificationAPIResponse(
            name=name,
            level=25,
            regiment=regiment,
            faction=faction,
            shard=shard,
            ingame_time=ingame_time,
            war=100,
            current_ingame_time=current_ingame_time,
        )

    def test_all_checks_pass(self) -> None:
        """Probar que aprueba cuando todo está correcto."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.NONE,
            ConfigKey.VERIFICATION_TIME_DIFF: 0,
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True
        assert reason is None

    def test_name_mismatch_exact_rejected(self) -> None:
        """Probar rechazo por nombre diferente en modo exacto."""
        request = self._create_request()
        api_response = self._create_api_response(name="DifferentName")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.EXACT,
            ConfigKey.REJECT_NAME_MISMATCH: "Nombre no coincide",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Nombre no coincide"

    def test_name_match_contains_approved(self) -> None:
        """Probar aprobación cuando nombre está contenido."""
        request = self._create_request()
        api_response = self._create_api_response(name="TestPlayer [TAG]")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.CONTAINS,
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True
        assert reason is None

    def test_name_match_contains_rejected(self) -> None:
        """Probar rechazo cuando nombre no está contenido."""
        request = self._create_request()
        api_response = self._create_api_response(name="CompletelyDifferent")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: NameMatchMode.CONTAINS,
            ConfigKey.REJECT_NAME_MISMATCH: "Nombre no coincide",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Nombre no coincide"

    def test_has_regiment_rejected_for_regular(self) -> None:
        """Probar rechazo por tener regimiento en verificación regular."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="SomeRegiment")
        config: dict[str, Any] = {
            ConfigKey.REJECT_HAS_REGIMENT: "Tiene regimiento",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Tiene regimiento"

    def test_has_regiment_allowed_for_ally(self) -> None:
        """Probar que tener regimiento está permitido para aliados."""
        request = self._create_request(verification_type=VerificationType.ALLY)
        api_response = self._create_api_response(regiment="SomeRegiment")
        config: dict[str, Any] = {}

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True
        assert reason is None

    def test_valid_regiment_configured_and_matches(self) -> None:
        """Probar aprobación cuando el regimiento coincide con el válido."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[7-HP#8707] 7th Hispanic Platoon")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "7-HP#8707",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True
        assert reason is None

    def test_valid_regiment_configured_but_different(self) -> None:
        """Probar rechazo cuando el regimiento no coincide con el válido."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[OTHER#1234] Other Regiment")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "7-HP#8707",
            ConfigKey.REJECT_HAS_REGIMENT: "Regimiento inválido",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Regimiento inválido"

    def test_valid_regiment_empty_rejects_any_regiment(self) -> None:
        """Probar que si no hay regimiento válido, rechaza cualquier regimiento."""
        request = self._create_request(verification_type=VerificationType.REGULAR)
        api_response = self._create_api_response(regiment="[7-HP#8707] 7th Hispanic Platoon")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_VALID_REGIMENT: "",
            ConfigKey.REJECT_HAS_REGIMENT: "Tiene regimiento",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Tiene regimiento"

    def test_time_diff_exceeded(self) -> None:
        """Probar rechazo por diferencia de tiempo excesiva."""
        request = self._create_request()
        api_response = self._create_api_response(
            ingame_time="100, 07:41",
            current_ingame_time="200, 08:34",  # 100 days diff
        )
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TIME_DIFF: 30,
            ConfigKey.REJECT_TIME_DIFF: "Captura antigua",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Captura antigua"

    def test_wrong_shard_rejected(self) -> None:
        """Probar rechazo por shard incorrecto."""
        request = self._create_request()
        api_response = self._create_api_response(shard="CHARLIE")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_SHARD: "ABLE",
            ConfigKey.REJECT_WRONG_SHARD: "Shard incorrecto, debe ser {shard}",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason is not None and "ABLE" in reason

    def test_wrong_faction_rejected(self) -> None:
        """Probar rechazo por facción incorrecta."""
        request = self._create_request()
        api_response = self._create_api_response(faction="wardens")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
            ConfigKey.REJECT_WRONG_FACTION: "Facción incorrecta",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is False
        assert reason == "Facción incorrecta"

    def test_correct_faction_approved(self) -> None:
        """Probar aprobación con facción correcta."""
        request = self._create_request()
        api_response = self._create_api_response(faction="colonial")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True
        assert reason is None

    def test_faction_case_insensitive(self) -> None:
        """Probar que la comparación de facción es case insensitive."""
        request = self._create_request()
        api_response = self._create_api_response(faction="COLONIAL")
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_FACTION: "colonial",
        }

        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True

    def test_legacy_boolean_true_match_name(self) -> None:
        """Probar compatibilidad con legacy boolean True para match_name."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: True,  # Legacy boolean
        }

        # Nombre coincide exactamente
        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="TestPlayer",
        )

        assert should_approve is True

    def test_legacy_boolean_false_match_name(self) -> None:
        """Probar compatibilidad con legacy boolean False para match_name."""
        request = self._create_request()
        api_response = self._create_api_response()
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_MATCH_NAME: False,  # Legacy boolean
        }

        # Nombre no coincide pero no importa porque está deshabilitado
        should_approve, reason = process_verification(
            request=request,
            api_response=api_response,
            config=config,
            member_display_name="DifferentName",
        )

        assert should_approve is True
