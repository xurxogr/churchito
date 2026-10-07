"""Tests for discord_bot/common/core/settings/cogs.py."""

import pytest
from pydantic import ValidationError

from discord_bot.common.core import AppSettings
from discord_bot.common.core.settings.cogs import COG_EXTENSIONS, CogsSettings


class TestCogsSettings:
    """Tests for CogsSettings."""

    def test_every_cog_is_enabled_by_default(self) -> None:
        """A config without a cogs block loads all extensions."""
        settings = CogsSettings()

        assert settings.enabled_extensions() == tuple(COG_EXTENSIONS.values())

    def test_disabled_cogs_are_left_out(self) -> None:
        """Only the cogs left on are returned, in load order."""
        settings = CogsSettings(
            verification=False, autoname=False, purge=False, roles=False, derived_roles=False
        )

        assert settings.enabled_extensions() == ("discord_bot.stockpile.cog",)

    def test_one_flag_per_known_cog(self) -> None:
        """The flag names match the extension table so the config reads as cog names."""
        assert set(CogsSettings.model_fields) == set(COG_EXTENSIONS)

    def test_unknown_cog_is_rejected(self) -> None:
        """A typo in the config fails at startup instead of being ignored."""
        with pytest.raises(ValidationError):
            CogsSettings(stockpiles=False)  # type: ignore[call-arg]

    def test_app_settings_exposes_cogs(self) -> None:
        """The block is reachable as settings.cogs with defaults."""
        settings = AppSettings(bot={"token": "t"})

        assert settings.cogs.stockpile is True
        assert len(settings.cogs.enabled_extensions()) == len(COG_EXTENSIONS)
