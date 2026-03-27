"""Tests for ConfigService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import ConfigSchemaService
from discord_bot.common.services.config_service import ConfigService


@pytest.fixture
def schema_service() -> ConfigSchemaService:
    """Create a schema service with test data.

    Returns:
        ConfigSchemaService: Schema service
    """
    service = ConfigSchemaService()
    service.register_schema(
        CogConfigSchema(
            cog_name="test_cog",
            display_name="Test Cog",
            options=[
                ConfigOption(
                    key="string_option",
                    name="String Option",
                    option_type=ConfigOptionType.STRING,
                    default="default_string",
                ),
                ConfigOption(
                    key="int_option",
                    name="Integer Option",
                    option_type=ConfigOptionType.INTEGER,
                    default=42,
                    min_value=0,
                    max_value=100,
                ),
                ConfigOption(
                    key="required_option",
                    name="Required Option",
                    option_type=ConfigOptionType.STRING,
                    required=True,
                ),
            ],
        )
    )
    return service


class TestConfigService:
    """Tests for ConfigService."""

    async def test_get_value_returns_default_when_not_set(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that get_value returns the default value."""
        config_service = ConfigService(test_session, schema_service)
        value = await config_service.get_value(123, "test_cog", "string_option")
        assert value == "default_string"

    async def test_get_value_returns_stored_value(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that get_value returns the stored value."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_value(123, "test_cog", "string_option", "custom_value")
        value = await config_service.get_value(123, "test_cog", "string_option")
        assert value == "custom_value"

    async def test_get_value_returns_none_for_unknown_option(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that get_value returns None for unknown option."""
        config_service = ConfigService(test_session, schema_service)
        value = await config_service.get_value(123, "unknown_cog", "unknown_option")
        assert value is None

    async def test_set_value_success(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that set_value saves correctly."""
        config_service = ConfigService(test_session, schema_service)

        success, error = await config_service.set_value(
            123, "test_cog", "string_option", "new_value"
        )
        assert success is True
        assert error is None

        value = await config_service.get_value(123, "test_cog", "string_option")
        assert value == "new_value"

    async def test_set_value_validation_error(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that set_value validates the value."""
        config_service = ConfigService(test_session, schema_service)

        success, error = await config_service.set_value(
            123,
            "test_cog",
            "int_option",
            150,  # Exceeds max_value
        )
        assert success is False
        assert error is not None
        assert "cannot exceed" in error

    async def test_set_value_updates_existing(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that set_value updates existing value."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_value(123, "test_cog", "string_option", "first")
        await config_service.set_value(123, "test_cog", "string_option", "second")

        value = await config_service.get_value(123, "test_cog", "string_option")
        assert value == "second"

    async def test_set_value_unknown_option(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test set_value for option without schema."""
        config_service = ConfigService(test_session, schema_service)

        success, error = await config_service.set_value(
            123, "unknown_cog", "unknown_option", "value"
        )
        assert success is True
        assert error is None

    async def test_get_all_config(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test get_all_config combines defaults and stored values."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_value(123, "test_cog", "string_option", "custom")

        config = await config_service.get_all_config(123, "test_cog")
        assert config["string_option"] == "custom"
        assert config["int_option"] == 42  # default

    async def test_get_all_config_unknown_cog(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test get_all_config for unknown cog."""
        config_service = ConfigService(test_session, schema_service)
        config = await config_service.get_all_config(123, "unknown_cog")
        assert config == {}

    async def test_reset_config(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test reset_config deletes all values."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_value(123, "test_cog", "string_option", "value1")
        await config_service.set_value(123, "test_cog", "int_option", 50)

        deleted = await config_service.reset_config(123, "test_cog")
        assert deleted == 2

        value = await config_service.get_value(123, "test_cog", "string_option")
        assert value == "default_string"

    async def test_reset_config_no_values(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test reset_config when there are no values."""
        config_service = ConfigService(test_session, schema_service)
        deleted = await config_service.reset_config(123, "test_cog")
        assert deleted == 0

    async def test_is_cog_enabled_default(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test is_cog_enabled returns default when there is no record."""
        config_service = ConfigService(test_session, schema_service)

        enabled = await config_service.is_cog_enabled(123, "test_cog", default=True)
        assert enabled is True

        enabled = await config_service.is_cog_enabled(123, "test_cog", default=False)
        assert enabled is False

    async def test_set_cog_enabled(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test set_cog_enabled."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_cog_enabled(123, "test_cog", False)
        enabled = await config_service.is_cog_enabled(123, "test_cog")
        assert enabled is False

        await config_service.set_cog_enabled(123, "test_cog", True)
        enabled = await config_service.is_cog_enabled(123, "test_cog")
        assert enabled is True

    async def test_set_cog_enabled_updates_existing(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that set_cog_enabled updates existing record."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_cog_enabled(123, "test_cog", True)
        await config_service.set_cog_enabled(123, "test_cog", False)

        enabled = await config_service.is_cog_enabled(123, "test_cog")
        assert enabled is False

    async def test_get_enabled_cogs(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test get_enabled_cogs."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_cog_enabled(123, "cog1", True)
        await config_service.set_cog_enabled(123, "cog2", False)
        await config_service.set_cog_enabled(123, "cog3", True)

        enabled_cogs = await config_service.get_enabled_cogs(123)
        assert enabled_cogs == {"cog1": True, "cog2": False, "cog3": True}

    async def test_get_enabled_cogs_empty(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test get_enabled_cogs when empty."""
        config_service = ConfigService(test_session, schema_service)
        enabled_cogs = await config_service.get_enabled_cogs(123)
        assert enabled_cogs == {}

    async def test_different_guilds_isolated(
        self, test_session: AsyncSession, schema_service: ConfigSchemaService
    ) -> None:
        """Test that different guilds have isolated configuration."""
        config_service = ConfigService(test_session, schema_service)

        await config_service.set_value(111, "test_cog", "string_option", "guild_111")
        await config_service.set_value(222, "test_cog", "string_option", "guild_222")

        value1 = await config_service.get_value(111, "test_cog", "string_option")
        value2 = await config_service.get_value(222, "test_cog", "string_option")

        assert value1 == "guild_111"
        assert value2 == "guild_222"
