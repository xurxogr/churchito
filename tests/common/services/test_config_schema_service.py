"""Tests for ConfigSchemaService."""

import pytest

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import ConfigSchemaService


@pytest.fixture
def schema_service() -> ConfigSchemaService:
    """Create a new ConfigSchemaService instance.

    Returns:
        ConfigSchemaService: Service instance
    """
    return ConfigSchemaService()


@pytest.fixture
def sample_schema() -> CogConfigSchema:
    """Create a sample schema.

    Returns:
        CogConfigSchema: Sample schema
    """
    return CogConfigSchema(
        cog_name="sample",
        display_name="Sample Cog",
        description="A sample cog for testing",
        options=[
            ConfigOption(
                key="option1",
                name="Option 1",
                option_type=ConfigOptionType.STRING,
                default="default_value",
            ),
            ConfigOption(
                key="option2",
                name="Option 2",
                option_type=ConfigOptionType.INTEGER,
                default=10,
            ),
        ],
    )


class TestConfigSchemaService:
    """Tests for ConfigSchemaService."""

    def test_register_schema_overwrites(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test that registering the same schema overwrites it."""
        schema_service.register_schema(sample_schema)

        new_schema = CogConfigSchema(
            cog_name="sample",
            display_name="Updated Sample",
        )
        schema_service.register_schema(new_schema)

        retrieved = schema_service.get_schema("sample")
        assert retrieved is not None
        assert retrieved.display_name == "Updated Sample"

    def test_unregister_schema_exists(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test unregistering an existing schema."""
        schema_service.register_schema(sample_schema)
        result = schema_service.unregister_schema("sample")
        assert result is True
        assert schema_service.get_schema("sample") is None

    def test_unregister_schema_not_exists(self, schema_service: ConfigSchemaService) -> None:
        """Test unregistering a non-existent schema."""
        result = schema_service.unregister_schema("nonexistent")
        assert result is False

    def test_get_schema_exists(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test getting an existing schema."""
        schema_service.register_schema(sample_schema)
        schema = schema_service.get_schema("sample")
        assert schema is not None
        assert schema.cog_name == "sample"

    def test_get_schema_not_exists(self, schema_service: ConfigSchemaService) -> None:
        """Test getting a non-existent schema."""
        schema = schema_service.get_schema("nonexistent")
        assert schema is None

    def test_get_all_schemas(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test getting all schemas."""
        schema_service.register_schema(sample_schema)

        another_schema = CogConfigSchema(
            cog_name="another",
            display_name="Another Cog",
        )
        schema_service.register_schema(another_schema)

        all_schemas = schema_service.get_all_schemas()
        assert len(all_schemas) == 2
        assert "sample" in all_schemas
        assert "another" in all_schemas

    def test_get_option_exists(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test getting an existing option."""
        schema_service.register_schema(sample_schema)
        option = schema_service.get_option("sample", "option1")
        assert option is not None
        assert option.key == "option1"

    def test_get_option_schema_not_exists(self, schema_service: ConfigSchemaService) -> None:
        """Test getting an option from a non-existent schema."""
        option = schema_service.get_option("nonexistent", "option1")
        assert option is None

    def test_get_option_not_exists(
        self, schema_service: ConfigSchemaService, sample_schema: CogConfigSchema
    ) -> None:
        """Test getting a non-existent option."""
        schema_service.register_schema(sample_schema)
        option = schema_service.get_option("sample", "nonexistent")
        assert option is None
