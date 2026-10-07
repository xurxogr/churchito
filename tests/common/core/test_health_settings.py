"""Tests for discord_bot/common/core/settings/health.py."""

import pytest
from pydantic import ValidationError

from discord_bot.common.core import AppSettings
from discord_bot.common.core.settings.health import MIN_INTERVAL_MINUTES, HealthSettings


class TestHealthSettings:
    """Tests for HealthSettings."""

    def test_disabled_by_default(self) -> None:
        """Without a health block the periodic check never runs."""
        settings = HealthSettings()

        assert settings.interval_minutes == 0
        assert settings.enabled is False

    def test_interval_enables_the_check(self) -> None:
        """Any accepted interval turns the check on."""
        settings = HealthSettings(interval_minutes=60)

        assert settings.enabled is True
        assert settings.interval_seconds == 3600

    def test_interval_below_minimum_is_rejected(self) -> None:
        """Short intervals would poll Discord too often, so they fail at startup."""
        with pytest.raises(ValidationError, match=str(MIN_INTERVAL_MINUTES)):
            HealthSettings(interval_minutes=MIN_INTERVAL_MINUTES - 1)

    def test_negative_interval_is_rejected(self) -> None:
        """Negative values are neither disabled nor a valid period."""
        with pytest.raises(ValidationError):
            HealthSettings(interval_minutes=-1)

    def test_unknown_key_is_rejected(self) -> None:
        """A typo in the block fails loudly instead of silently disabling the check."""
        with pytest.raises(ValidationError):
            HealthSettings(interval=10)  # type: ignore[call-arg]

    def test_app_settings_exposes_health(self) -> None:
        """The block hangs off settings.health with defaults."""
        settings = AppSettings(bot={"token": "t"})

        assert settings.health.enabled is False
