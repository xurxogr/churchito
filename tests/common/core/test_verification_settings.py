"""Tests para discord_bot/common/core/settings/verification.py."""

from discord_bot.common.core.settings.verification import VerificationSettings


class TestVerificationSettings:
    """Tests para VerificationSettings."""

    def test_default_values(self) -> None:
        """Probar valores por defecto."""
        settings = VerificationSettings()

        assert settings.api_url == ""
        assert settings.api_key == ""
        assert settings.api_timeout == 30

    def test_custom_values(self) -> None:
        """Probar valores personalizados."""
        settings = VerificationSettings(
            api_url="https://api.example.com/verify",
            api_key="test-key",
            api_timeout=60,
        )

        assert settings.api_url == "https://api.example.com/verify"
        assert settings.api_key == "test-key"
        assert settings.api_timeout == 60

    def test_api_url_empty_disables_verification(self) -> None:
        """Probar que URL vacía indica verificación desactivada."""
        settings = VerificationSettings(api_url="")

        # Empty string is falsy, used to check if API is configured
        assert not settings.api_url
