"""Tests for DefaultMigrator."""

from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.models.guild_config import GuildConfig
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import ConfigSchemaService
from discord_bot.i18n import I18nService
from discord_bot.i18n.default_migrator import (
    TRANSLATABLE_TYPES,
    DefaultMigrator,
    get_default_migrator,
)


class TestDefaultMigratorInitialization:
    """Tests for DefaultMigrator initialization."""

    def test_default_migrator_initializes_with_default_services(self) -> None:
        """Test that DefaultMigrator initializes with default services."""
        migrator = DefaultMigrator()

        assert migrator._i18n is not None
        assert isinstance(migrator._i18n, I18nService)
        assert migrator._schema is not None
        assert isinstance(migrator._schema, ConfigSchemaService)

    def test_default_migrator_accepts_custom_services(self) -> None:
        """Test that DefaultMigrator accepts custom services."""
        custom_i18n = I18nService()
        custom_schema = ConfigSchemaService()

        migrator = DefaultMigrator(i18n_service=custom_i18n, schema_service=custom_schema)

        assert migrator._i18n is custom_i18n
        assert migrator._schema is custom_schema


class TestTranslatableTypes:
    """Tests for TRANSLATABLE_TYPES constant."""

    def test_translatable_types_includes_string(self) -> None:
        """Test that STRING type is translatable."""
        assert ConfigOptionType.STRING in TRANSLATABLE_TYPES

    def test_translatable_types_includes_textarea(self) -> None:
        """Test that TEXTAREA type is translatable."""
        assert ConfigOptionType.TEXTAREA in TRANSLATABLE_TYPES

    def test_translatable_types_excludes_boolean(self) -> None:
        """Test that BOOLEAN type is not translatable."""
        assert ConfigOptionType.BOOLEAN not in TRANSLATABLE_TYPES

    def test_translatable_types_excludes_integer(self) -> None:
        """Test that INTEGER type is not translatable."""
        assert ConfigOptionType.INTEGER not in TRANSLATABLE_TYPES


class TestDefaultMigratorMigrateDefaults:
    """Tests for DefaultMigrator migrate_defaults method."""

    async def test_migrate_defaults_same_language_returns_zero(
        self, test_session: AsyncSession
    ) -> None:
        """Test that migration with same language returns 0."""
        migrator = DefaultMigrator()

        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="en"
        )

        assert count == 0

    async def test_migrate_defaults_no_translatable_options_returns_zero(
        self, test_session: AsyncSession
    ) -> None:
        """Test that migration with no translatable options returns 0."""
        # Mock schema service with no translatable options
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test",
            description="Test",
            icon="🧪",
            toggleable=True,
            options=[
                ConfigOption(
                    key="boolean_option",
                    name="Boolean",
                    description="A boolean",
                    option_type=ConfigOptionType.BOOLEAN,
                    default=True,
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"test": schema}

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        assert count == 0

    async def test_migrate_defaults_migrates_matching_value(
        self, test_session: AsyncSession
    ) -> None:
        """Test that matching default value is migrated."""
        # Setup: Create schema with translatable option
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button Text",
                    description="Text for button",
                    option_type=ConfigOptionType.STRING,
                    default="Default Text",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        # Create existing config with English default
        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",  # English default
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Verify migration happened
        assert count == 1

        # Verify value was updated
        await test_session.refresh(config)
        assert config.value == "Verificar"  # Spanish default

    async def test_migrate_defaults_skips_customized_value(
        self, test_session: AsyncSession
    ) -> None:
        """Test that customized value is not migrated."""
        # Setup
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button Text",
                    description="Text for button",
                    option_type=ConfigOptionType.STRING,
                    default="Default Text",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        # Create config with custom value
        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Custom Button Text",  # Custom value, not default
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Verify no migration happened
        assert count == 0

        # Verify value unchanged
        await test_session.refresh(config)
        assert config.value == "Custom Button Text"

    async def test_migrate_defaults_creates_new_config_if_none_exists(
        self, test_session: AsyncSession
    ) -> None:
        """Test that migration creates new config when none exists."""
        # Setup
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button Text",
                    description="Text for button",
                    option_type=ConfigOptionType.STRING,
                    default="Default Text",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration (no existing config)
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should create new config with Spanish default
        assert count == 1

    async def test_migrate_defaults_skips_options_with_none_default(
        self, test_session: AsyncSession
    ) -> None:
        """Test that options with None default are skipped."""
        # Setup
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test",
            description="Test",
            icon="🧪",
            toggleable=True,
            options=[
                ConfigOption(
                    key="optional_text",
                    name="Optional Text",
                    description="Optional",
                    option_type=ConfigOptionType.STRING,
                    default=None,  # No default
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"test": schema}

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should skip this option
        assert count == 0

    async def test_migrate_defaults_skips_when_defaults_are_same(
        self, test_session: AsyncSession
    ) -> None:
        """Test that migration skips when old and new defaults are identical."""
        # Setup with option that has same default in both languages
        mock_i18n = MagicMock(spec=I18nService)
        mock_i18n.get_translated_default.return_value = "Same Value"

        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test",
            description="Test",
            icon="🧪",
            toggleable=True,
            options=[
                ConfigOption(
                    key="text_option",
                    name="Text",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Same Value",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"test": schema}

        migrator = DefaultMigrator(i18n_service=mock_i18n, schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should skip since defaults are same
        assert count == 0

    async def test_migrate_defaults_handles_multiple_options(
        self, test_session: AsyncSession
    ) -> None:
        """Test migration with multiple translatable options."""
        # Setup
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button Text",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                ),
                ConfigOption(
                    key="verify_ally_button_text",
                    name="Ally Button",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                ),
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        # Create configs with English defaults
        config1 = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",
        )
        config2 = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_ally_button_text",
            value="Verify as Ally",
        )
        test_session.add_all([config1, config2])
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should migrate both
        assert count == 2

    async def test_migrate_defaults_handles_multiple_cogs(self, test_session: AsyncSession) -> None:
        """Test migration across multiple cogs."""
        # Setup
        mock_schema_service = MagicMock(spec=ConfigSchemaService)

        schema1 = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                )
            ],
        )

        schema2 = CogConfigSchema(
            cog_name="purge",
            display_name="Purge",
            description="Test",
            icon="🧹",
            toggleable=True,
            options=[
                ConfigOption(
                    key="mod_button_text",
                    name="Button",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                )
            ],
        )

        mock_schema_service.get_all_schemas.return_value = {
            "verification": schema1,
            "purge": schema2,
        }

        # Create configs
        config1 = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",
        )
        config2 = GuildConfig(
            guild_id=123, cog_name="purge", key="mod_button_text", value="🔑 Authorize purge"
        )
        test_session.add_all([config1, config2])
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should migrate from both cogs
        assert count == 2


class TestDefaultMigratorGetTranslatedDefault:
    """Tests for DefaultMigrator _get_translated_default method."""

    def test_get_translated_default_delegates_to_i18n(self) -> None:
        """Test that method delegates to I18nService."""
        mock_i18n = MagicMock(spec=I18nService)
        mock_i18n.get_translated_default.return_value = "Translated Value"

        migrator = DefaultMigrator(i18n_service=mock_i18n)

        result = migrator._get_translated_default(
            cog_name="verification",
            option_key="test_key",
            lang="en",
            original_default="Original",
        )

        mock_i18n.get_translated_default.assert_called_once_with(
            cog_name="verification",
            key="test_key",
            lang="en",
            fallback="Original",
        )
        assert result == "Translated Value"


class TestDefaultMigratorGetCurrentValue:
    """Tests for DefaultMigrator _get_current_value method."""

    async def test_get_current_value_existing_config(self, test_session: AsyncSession) -> None:
        """Test getting current value from existing config."""
        # Create config
        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="test_key",
            value="Current Value",
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator()

        result = await migrator._get_current_value(
            session=test_session,
            guild_id=123,
            cog_name="verification",
            key="test_key",
        )

        assert result == "Current Value"

    async def test_get_current_value_nonexistent_config_returns_none(
        self, test_session: AsyncSession
    ) -> None:
        """Test that nonexistent config returns None."""
        migrator = DefaultMigrator()

        result = await migrator._get_current_value(
            session=test_session,
            guild_id=123,
            cog_name="verification",
            key="nonexistent",
        )

        assert result is None


class TestDefaultMigratorUpdateValue:
    """Tests for DefaultMigrator _update_value method."""

    async def test_update_value_existing_config(self, test_session: AsyncSession) -> None:
        """Test updating existing config."""
        # Create existing config
        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="test_key",
            value="Old Value",
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator()

        result = await migrator._update_value(
            session=test_session,
            guild_id=123,
            cog_name="verification",
            key="test_key",
            new_value="New Value",
        )

        assert result is True

        # Need to flush to persist changes
        await test_session.flush()

        # Verify update
        await test_session.refresh(config)
        assert config.value == "New Value"

    async def test_update_value_creates_new_config_if_none_exists(
        self, test_session: AsyncSession
    ) -> None:
        """Test creating new config when none exists."""
        migrator = DefaultMigrator()

        result = await migrator._update_value(
            session=test_session,
            guild_id=123,
            cog_name="verification",
            key="new_key",
            new_value="New Value",
        )

        assert result is True

        # Verify new config was created
        from sqlalchemy import select

        stmt = select(GuildConfig).where(
            GuildConfig.guild_id == 123,
            GuildConfig.cog_name == "verification",
            GuildConfig.key == "new_key",
        )
        db_result = await test_session.execute(stmt)
        config = db_result.scalar_one_or_none()

        assert config is not None
        assert config.value == "New Value"


class TestDefaultMigratorValuesMatch:
    """Tests for DefaultMigrator _values_match method."""

    def test_values_match_identical_strings(self) -> None:
        """Test that identical strings match."""
        migrator = DefaultMigrator()

        assert migrator._values_match("test", "test") is True

    def test_values_match_strings_with_whitespace(self) -> None:
        """Test that strings with different whitespace match after strip."""
        migrator = DefaultMigrator()

        assert migrator._values_match("  test  ", "test") is True
        assert migrator._values_match("test", "  test  ") is True
        assert migrator._values_match("  test  ", "  test  ") is True

    def test_values_match_different_strings(self) -> None:
        """Test that different strings don't match."""
        migrator = DefaultMigrator()

        assert migrator._values_match("test1", "test2") is False

    def test_values_match_empty_strings(self) -> None:
        """Test that empty strings match."""
        migrator = DefaultMigrator()

        assert migrator._values_match("", "") is True
        assert migrator._values_match("  ", "") is True

    def test_values_match_non_string_types(self) -> None:
        """Test matching with non-string types."""
        migrator = DefaultMigrator()

        assert migrator._values_match(42, 42) is True
        assert migrator._values_match(42, 43) is False
        assert migrator._values_match(True, True) is True
        assert migrator._values_match(True, False) is False

    def test_values_match_mixed_types(self) -> None:
        """Test matching with mixed types."""
        migrator = DefaultMigrator()

        assert migrator._values_match("42", 42) is False
        assert migrator._values_match(None, None) is True
        assert migrator._values_match("test", None) is False

    def test_values_match_list_types(self) -> None:
        """Test matching with list types."""
        migrator = DefaultMigrator()

        assert migrator._values_match([1, 2, 3], [1, 2, 3]) is True
        assert migrator._values_match([1, 2], [1, 2, 3]) is False

    def test_values_match_dict_types(self) -> None:
        """Test matching with dict types."""
        migrator = DefaultMigrator()

        assert migrator._values_match({"a": 1}, {"a": 1}) is True
        assert migrator._values_match({"a": 1}, {"a": 2}) is False


class TestDefaultMigratorEdgeCases:
    """Edge case tests for DefaultMigrator."""

    async def test_migrate_defaults_with_textarea_type(self, test_session: AsyncSession) -> None:
        """Test that TEXTAREA type is migrated."""
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verification_panel_message",
                    name="Panel Message",
                    description="Message",
                    option_type=ConfigOptionType.TEXTAREA,
                    default="Default message",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        # Create config with English default
        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verification_panel_message",
            value=(
                "**Welcome to {server_name}!**\n\n"
                "To access the server, you need to verify. "
                "Click the corresponding button to get started."
            ),
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Should migrate
        assert count == 1

    async def test_migrate_defaults_empty_schemas(self, test_session: AsyncSession) -> None:
        """Test migration with no schemas."""
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        mock_schema_service.get_all_schemas.return_value = {}

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        assert count == 0

    async def test_migrate_defaults_flushes_session(self, test_session: AsyncSession) -> None:
        """Test that migration flushes the session when changes made."""
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        config = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",
        )
        test_session.add(config)
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Execute migration
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        # Session should be flushed (changes persisted but not committed)
        assert count > 0

    async def test_migrate_defaults_different_guild_ids(self, test_session: AsyncSession) -> None:
        """Test that migration only affects specified guild."""
        mock_schema_service = MagicMock(spec=ConfigSchemaService)
        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Test",
            icon="🔒",
            toggleable=True,
            options=[
                ConfigOption(
                    key="verify_button_text",
                    name="Button",
                    description="Text",
                    option_type=ConfigOptionType.STRING,
                    default="Default",
                )
            ],
        )
        mock_schema_service.get_all_schemas.return_value = {"verification": schema}

        # Create configs for different guilds
        config1 = GuildConfig(
            guild_id=123,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",
        )
        config2 = GuildConfig(
            guild_id=456,
            cog_name="verification",
            key="verify_button_text",
            value="Verify",
        )
        test_session.add_all([config1, config2])
        await test_session.commit()

        migrator = DefaultMigrator(schema_service=mock_schema_service)

        # Migrate only guild 123
        count = await migrator.migrate_defaults(
            session=test_session, guild_id=123, old_lang="en", new_lang="es"
        )

        assert count == 1

        # Verify only guild 123 was changed
        await test_session.refresh(config1)
        await test_session.refresh(config2)

        assert config1.value == "Verificar"
        assert config2.value == "Verify"  # Unchanged


class TestGetDefaultMigrator:
    """Tests for get_default_migrator function."""

    def test_get_default_migrator_returns_instance(self) -> None:
        """Test that get_default_migrator returns DefaultMigrator instance."""
        migrator = get_default_migrator()

        assert isinstance(migrator, DefaultMigrator)

    def test_get_default_migrator_returns_new_instance(self) -> None:
        """Test that get_default_migrator returns new instance each time."""
        migrator1 = get_default_migrator()
        migrator2 = get_default_migrator()

        # Should be different instances (not cached)
        assert migrator1 is not migrator2
