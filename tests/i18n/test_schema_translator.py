"""Tests for SchemaTranslator."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.i18n import I18nService
from discord_bot.i18n.schema_translator import SchemaTranslator, get_schema_translator


class TestSchemaTranslatorInitialization:
    """Tests for SchemaTranslator initialization."""

    def test_schema_translator_initializes_with_default_service(self) -> None:
        """Test that SchemaTranslator initializes with default I18nService."""
        translator = SchemaTranslator()

        assert translator._i18n is not None
        assert isinstance(translator._i18n, I18nService)

    def test_schema_translator_accepts_custom_service(self) -> None:
        """Test that SchemaTranslator accepts custom I18nService."""
        custom_service = I18nService()
        translator = SchemaTranslator(i18n_service=custom_service)

        assert translator._i18n is custom_service


class TestSchemaTranslatorTranslateSchema:
    """Tests for SchemaTranslator translate_schema method."""

    def test_translate_schema_basic_fields(self) -> None:
        """Test translation of basic schema fields."""
        translator = SchemaTranslator()

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification (untranslated)",
            description="Verification system (untranslated)",
            icon="🔒",
            toggleable=True,
            options=[],
        )

        result = translator.translate_schema(schema, "en")

        assert result["cog_name"] == "verification"
        assert result["display_name"] == "Verification"
        assert result["description"] == "User verification system with screenshots"
        assert result["icon"] == "🔒"
        assert result["toggleable"] is True

    def test_translate_schema_preserves_untranslated_fields(self) -> None:
        """Test that untranslated fields fall back to original."""
        translator = SchemaTranslator()

        schema = CogConfigSchema(
            cog_name="unknown_cog",
            display_name="Original Display Name",
            description="Original Description",
            icon="📦",
            toggleable=False,
            options=[],
        )

        result = translator.translate_schema(schema, "en")

        # Should fall back to original values
        assert result["display_name"] == "Original Display Name"
        assert result["description"] == "Original Description"

    def test_translate_schema_to_spanish(self) -> None:
        """Test schema translation to Spanish."""
        translator = SchemaTranslator()

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Verification system",
            icon="🔒",
            toggleable=True,
            options=[],
        )

        result = translator.translate_schema(schema, "es")

        assert result["display_name"] == "Verificación"
        assert (
            result["description"] == "Sistema de verificación de usuarios con capturas de pantalla"
        )

    def test_translate_schema_with_options(self) -> None:
        """Test schema translation with config options."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="verification_enabled",
            name="Verification Enabled (untranslated)",
            description="Enable verification (untranslated)",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
        )

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Verification system",
            icon="🔒",
            toggleable=True,
            options=[option],
        )

        result = translator.translate_schema(schema, "en")

        assert len(result["options"]) == 1
        translated_option = result["options"][0]
        assert translated_option["key"] == "verification_enabled"
        assert translated_option["name"] == "Verification enabled"
        assert translated_option["description"] == "Enable or disable the verification system"

    def test_translate_schema_empty_options(self) -> None:
        """Test schema translation with no options."""
        translator = SchemaTranslator()

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="Verification system",
            icon="🔒",
            toggleable=True,
            options=[],
        )

        result = translator.translate_schema(schema, "en")

        assert result["options"] == []


class TestSchemaTranslatorTranslateOption:
    """Tests for SchemaTranslator _translate_option method."""

    def test_translate_option_basic_fields(self) -> None:
        """Test translation of basic option fields."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="verification_enabled",
            name="Untranslated Name",
            description="Untranslated Description",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["key"] == "verification_enabled"
        assert result["name"] == "Verification enabled"
        assert result["description"] == "Enable or disable the verification system"
        assert result["type"] == ConfigOptionType.BOOLEAN.value
        assert result["default"] is True
        assert result["required"] is False

    def test_translate_option_with_section(self) -> None:
        """Test option translation with section."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
            section="Common",
        )

        sections_trans = {"Common": "Común"}

        result = translator._translate_option(
            cog_name="purge",
            option=option,
            lang="es",
            sections_trans=sections_trans,
            groups_trans={},
        )

        assert result["section"] == "Común"

    def test_translate_option_with_group(self) -> None:
        """Test option translation with group."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
            group="Options",
        )

        groups_trans = {"Options": "Opciones"}

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="es",
            sections_trans={},
            groups_trans=groups_trans,
        )

        assert result["group"] == "Opciones"

    def test_translate_option_without_section_or_group(self) -> None:
        """Test option translation without section or group."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["section"] is None
        assert result["group"] is None

    def test_translate_option_untranslated_section_uses_original(self) -> None:
        """Test that untranslated section falls back to original."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
            section="UntranslatedSection",
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["section"] == "UntranslatedSection"

    def test_translate_option_with_min_max_values(self) -> None:
        """Test option translation preserves min/max values."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_number",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.INTEGER,
            min_value=0,
            max_value=100,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["min_value"] == 0
        assert result["max_value"] == 100

    def test_translate_option_with_max_length(self) -> None:
        """Test option translation preserves max_length."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_string",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
            max_length=255,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["max_length"] == 255

    def test_translate_option_with_placeholders(self) -> None:
        """Test option translation preserves placeholders."""
        translator = SchemaTranslator()

        placeholders = ["server_name", "user_name"]
        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.TEXTAREA,
            placeholders=placeholders,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["placeholders"] == placeholders

    def test_translate_option_required_field(self) -> None:
        """Test option translation preserves required flag."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
            required=True,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["required"] is True


class TestSchemaTranslatorTranslateChoices:
    """Tests for SchemaTranslator _translate_choices method."""

    def test_translate_choices_basic(self) -> None:
        """Test translation of basic choices."""
        translator = SchemaTranslator()

        choices = [("Colonial", "colonial"), ("Warden", "warden")]

        result = translator._translate_choices(
            cog_name="verification",
            option_key="verification_faction",
            choices=choices,
            lang="en",
        )

        assert len(result) == 2
        assert result[0] == ("Colonial", "colonial")
        assert result[1] == ("Warden", "warden")

    def test_translate_choices_spanish(self) -> None:
        """Test translation of choices to Spanish."""
        translator = SchemaTranslator()

        choices = [("Blue", "blue"), ("Grey", "grey")]

        result = translator._translate_choices(
            cog_name="purge",
            option_key="mod_button_color",
            choices=choices,
            lang="es",
        )

        # Check if translations exist in Spanish locale
        assert len(result) == 2
        assert result[0][1] == "blue"  # Value should remain unchanged
        assert result[1][1] == "grey"

    def test_translate_choices_untranslated_uses_original(self) -> None:
        """Test that untranslated choices use original labels."""
        translator = SchemaTranslator()

        choices = [("UntranslatedLabel", "value")]

        result = translator._translate_choices(
            cog_name="verification",
            option_key="some_option",
            choices=choices,
            lang="en",
        )

        assert result[0] == ("UntranslatedLabel", "value")

    def test_translate_choices_empty_list(self) -> None:
        """Test translation of empty choices list."""
        translator = SchemaTranslator()

        result = translator._translate_choices(
            cog_name="verification",
            option_key="some_option",
            choices=[],
            lang="en",
        )

        assert result == []

    def test_translate_choices_from_cog_level(self) -> None:
        """Test that choices can be translated from cog-level translations."""
        translator = SchemaTranslator()

        # These choices should come from cogs.verification.choices
        choices = [("Do not check", "none"), ("Exact", "exact")]

        result = translator._translate_choices(
            cog_name="verification",
            option_key="verification_match_name",
            choices=choices,
            lang="en",
        )

        assert len(result) == 2
        # Values should be preserved
        assert result[0][1] == "none"
        assert result[1][1] == "exact"

    def test_translate_choices_option_specific_takes_priority(self) -> None:
        """Test that option-specific translations take priority over cog-level."""
        translator = SchemaTranslator()

        # Mock scenario where same label exists at both levels
        translator._i18n._translations["test"] = {
            "cogs": {
                "test_cog": {
                    "choices": {"Label": "Cog Level Translation"},
                    "options": {"test_option": {"choices": {"Label": "Option Level Translation"}}},
                }
            }
        }

        choices = [("Label", "value")]

        result = translator._translate_choices(
            cog_name="test_cog",
            option_key="test_option",
            choices=choices,
            lang="test",
        )

        # Should use option-specific translation
        assert result[0][0] == "Option Level Translation"


class TestSchemaTranslatorTranslateColumns:
    """Tests for SchemaTranslator _translate_columns method."""

    def test_translate_columns_basic(self) -> None:
        """Test translation of table columns."""
        translator = SchemaTranslator()

        columns = [
            {"key": "from_role", "name": "Source Role"},
            {"key": "to_role", "name": "Target Role"},
        ]

        result = translator._translate_columns(
            cog_name="purge",
            columns=columns,
            lang="en",
        )

        assert len(result) == 2
        assert result[0]["key"] == "from_role"
        assert result[0]["name"] == "Source role"
        assert result[1]["key"] == "to_role"
        assert result[1]["name"] == "Target role"

    def test_translate_columns_spanish(self) -> None:
        """Test translation of columns to Spanish."""
        translator = SchemaTranslator()

        columns = [
            {"key": "from_role", "name": "From Role"},
            {"key": "to_role", "name": "To Role"},
        ]

        result = translator._translate_columns(
            cog_name="purge",
            columns=columns,
            lang="es",
        )

        assert result[0]["name"] == "Rol origen"
        assert result[1]["name"] == "Rol destino"

    def test_translate_columns_untranslated_uses_original(self) -> None:
        """Test that untranslated columns use original names."""
        translator = SchemaTranslator()

        columns = [{"key": "unknown_column", "name": "Original Name"}]

        result = translator._translate_columns(
            cog_name="purge",
            columns=columns,
            lang="en",
        )

        assert result[0]["name"] == "Original Name"

    def test_translate_columns_preserves_other_fields(self) -> None:
        """Test that other column fields are preserved."""
        translator = SchemaTranslator()

        columns = [
            {
                "key": "from_role",
                "name": "From",
                "type": "role",
                "required": True,
                "width": 100,
            }
        ]

        result = translator._translate_columns(
            cog_name="purge",
            columns=columns,
            lang="en",
        )

        assert result[0]["type"] == "role"
        assert result[0]["required"] is True
        assert result[0]["width"] == 100

    def test_translate_columns_empty_list(self) -> None:
        """Test translation of empty columns list."""
        translator = SchemaTranslator()

        result = translator._translate_columns(
            cog_name="purge",
            columns=[],
            lang="en",
        )

        assert result == []

    def test_translate_columns_missing_key_field(self) -> None:
        """Test columns without key field are handled."""
        translator = SchemaTranslator()

        columns = [{"name": "Column Without Key"}]

        result = translator._translate_columns(
            cog_name="purge",
            columns=columns,
            lang="en",
        )

        # Should return column unchanged
        assert result[0]["name"] == "Column Without Key"


class TestSchemaTranslatorOptionWithChoices:
    """Tests for translating options with choices."""

    def test_translate_option_with_choices(self) -> None:
        """Test that option with choices translates correctly."""
        translator = SchemaTranslator()

        choices = [("Blue", "blue"), ("Red", "red")]
        option = ConfigOption(
            key="mod_button_color",
            name="Button Color",
            description="Color of the button",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=choices,
        )

        result = translator._translate_option(
            cog_name="purge",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["choices"] is not None
        assert len(result["choices"]) == 2

    def test_translate_option_without_choices(self) -> None:
        """Test that option without choices has None for choices."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["choices"] is None


class TestSchemaTranslatorOptionWithColumns:
    """Tests for translating options with table columns."""

    def test_translate_option_with_columns(self) -> None:
        """Test that option with columns translates correctly."""
        translator = SchemaTranslator()

        columns = [
            {"key": "from_role", "name": "From"},
            {"key": "to_role", "name": "To"},
        ]
        option = ConfigOption(
            key="war_promotions",
            name="Promotions",
            description="Role promotions",
            option_type=ConfigOptionType.TABLE,
            columns=columns,
        )

        result = translator._translate_option(
            cog_name="purge",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["columns"] is not None
        assert len(result["columns"]) == 2

    def test_translate_option_without_columns(self) -> None:
        """Test that option without columns has None for columns."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="test_option",
            name="Test",
            description="Test",
            option_type=ConfigOptionType.STRING,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["columns"] is None


class TestSchemaTranslatorGetTranslatedDefault:
    """Tests for SchemaTranslator get_translated_default method."""

    def test_get_translated_default_existing_translation(self) -> None:
        """Test getting translated default value."""
        translator = SchemaTranslator()

        result = translator.get_translated_default(
            cog_name="verification",
            option_key="verify_button_text",
            lang="en",
            original_default="Original",
        )

        assert result == "Verify"

    def test_get_translated_default_spanish(self) -> None:
        """Test getting translated default in Spanish."""
        translator = SchemaTranslator()

        result = translator.get_translated_default(
            cog_name="verification",
            option_key="verify_button_text",
            lang="es",
            original_default="Original",
        )

        assert result == "Verificar"

    def test_get_translated_default_missing_returns_original(self) -> None:
        """Test that missing translation returns original default."""
        translator = SchemaTranslator()

        result = translator.get_translated_default(
            cog_name="nonexistent",
            option_key="nonexistent",
            lang="en",
            original_default="Original Default",
        )

        assert result == "Original Default"

    def test_get_translated_default_with_none_original(self) -> None:
        """Test that None original default is returned when no translation."""
        translator = SchemaTranslator()

        result = translator.get_translated_default(
            cog_name="nonexistent",
            option_key="nonexistent",
            lang="en",
            original_default=None,
        )

        assert result is None


class TestSchemaTranslatorEdgeCases:
    """Edge case tests for SchemaTranslator."""

    def test_translate_schema_with_complex_nested_structure(self) -> None:
        """Test schema translation with deeply nested options."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="verification_panel_message",
            name="Panel Message",
            description="Message for panel",
            option_type=ConfigOptionType.TEXTAREA,
            default="Default message",
            section="Verification Panel",
            group="Options",
            placeholders=["server_name", "user_name"],
            max_length=2000,
        )

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="System",
            icon="🔒",
            toggleable=True,
            options=[option],
        )

        result = translator.translate_schema(schema, "en")

        # Verify all nested fields are properly translated/preserved
        assert result["options"][0]["key"] == "verification_panel_message"
        assert result["options"][0]["max_length"] == 2000
        assert len(result["options"][0]["placeholders"]) == 2

    def test_translate_option_all_optional_fields_none(self) -> None:
        """Test option translation when all optional fields are None."""
        translator = SchemaTranslator()

        option = ConfigOption(
            key="minimal_option",
            name="Minimal",
            description="Description",
            option_type=ConfigOptionType.STRING,
            section=None,
            group=None,
            choices=None,
            columns=None,
            min_value=None,
            max_value=None,
            max_length=None,
            placeholders=None,
        )

        result = translator._translate_option(
            cog_name="verification",
            option=option,
            lang="en",
            sections_trans={},
            groups_trans={},
        )

        assert result["section"] is None
        assert result["group"] is None
        assert result["choices"] is None
        assert result["columns"] is None
        assert result["min_value"] is None
        assert result["max_value"] is None
        assert result["max_length"] is None
        assert result["placeholders"] is None

    def test_translate_schema_multiple_options(self) -> None:
        """Test schema translation with multiple options."""
        translator = SchemaTranslator()

        options = [
            ConfigOption(
                key="option1",
                name="Option 1",
                description="Desc 1",
                option_type=ConfigOptionType.STRING,
            ),
            ConfigOption(
                key="option2",
                name="Option 2",
                description="Desc 2",
                option_type=ConfigOptionType.BOOLEAN,
            ),
            ConfigOption(
                key="option3",
                name="Option 3",
                description="Desc 3",
                option_type=ConfigOptionType.INTEGER,
            ),
        ]

        schema = CogConfigSchema(
            cog_name="verification",
            display_name="Verification",
            description="System",
            icon="🔒",
            toggleable=True,
            options=options,
        )

        result = translator.translate_schema(schema, "en")

        assert len(result["options"]) == 3
        assert result["options"][0]["key"] == "option1"
        assert result["options"][1]["key"] == "option2"
        assert result["options"][2]["key"] == "option3"


class TestGetSchemaTranslator:
    """Tests for get_schema_translator function."""

    def test_get_schema_translator_returns_instance(self) -> None:
        """Test that get_schema_translator returns SchemaTranslator instance."""
        translator = get_schema_translator()

        assert isinstance(translator, SchemaTranslator)

    def test_get_schema_translator_returns_new_instance(self) -> None:
        """Test that get_schema_translator returns new instance each time."""
        translator1 = get_schema_translator()
        translator2 = get_schema_translator()

        # Should be different instances (not cached)
        assert translator1 is not translator2
