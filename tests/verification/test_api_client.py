"""Tests para discord_bot/verification/api_client.py."""

from discord_bot.verification.api_client import VerificationAPIResponse


class TestVerificationAPIResponse:
    """Tests para VerificationAPIResponse."""

    def test_from_dict_all_fields(self) -> None:
        """Probar creación desde diccionario con todos los campos."""
        data = {
            "name": "TestPlayer",
            "level": 25,
            "regiment": "TestRegiment",
            "faction": "colonial",
            "shard": "ABLE",
            "ingame_time": "268, 07:41",
            "war": 100,
            "current_ingame_time": "278, 08:34",
        }

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == "TestPlayer"
        assert response.level == 25
        assert response.regiment == "TestRegiment"
        assert response.faction == "colonial"
        assert response.shard == "ABLE"
        assert response.ingame_time == "268, 07:41"
        assert response.war == 100
        assert response.current_ingame_time == "278, 08:34"

    def test_from_dict_missing_fields(self) -> None:
        """Probar creación desde diccionario con campos faltantes."""
        data = {
            "name": "TestPlayer",
        }

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == "TestPlayer"
        assert response.level == 0
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == ""
        assert response.ingame_time == ""
        assert response.war == 0
        assert response.current_ingame_time == ""

    def test_from_dict_empty(self) -> None:
        """Probar creación desde diccionario vacío."""
        data: dict[str, object] = {}

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == ""
        assert response.level == 0
        assert response.regiment == ""
