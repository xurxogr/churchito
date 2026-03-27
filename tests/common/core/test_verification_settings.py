"""Tests for discord_bot/common/core/settings/verification.py."""

from discord_bot.common.core.settings.verification import VerificationSettings


class TestVerificationSettings:
    """Tests for VerificationSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = VerificationSettings()

        assert settings.api_url == ""
        assert settings.api_key == ""
        assert settings.api_timeout == 30

    def test_custom_values(self) -> None:
        """Test custom values."""
        settings = VerificationSettings(
            api_url="https://api.example.com/verify",
            api_key="test-key",
            api_timeout=60,
        )

        assert settings.api_url == "https://api.example.com/verify"
        assert settings.api_key == "test-key"
        assert settings.api_timeout == 60

    def test_api_url_empty_disables_verification(self) -> None:
        """Test that empty URL indicates verification is disabled."""
        settings = VerificationSettings(api_url="")

        # Empty string is falsy, used to check if API is configured
        assert not settings.api_url
