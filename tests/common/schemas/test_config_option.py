"""Tests for ConfigOption."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption


class TestConfigOptionValidation:
    """Tests for ConfigOption validation."""

    def test_validate_none_value_required(self) -> None:
        """Test validation of None when required."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            required=True,
        )
        is_valid, error = option.validate_value(None)
        assert is_valid is False
        assert error is not None and "is required" in error

    def test_validate_none_value_not_required(self) -> None:
        """Test validation of None when not required."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            required=False,
        )
        is_valid, error = option.validate_value(None)
        assert is_valid is True
        assert error is None

    def test_validate_string_valid(self) -> None:
        """Test validation of valid string."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            max_length=10,
        )
        is_valid, error = option.validate_value("hello")
        assert is_valid is True
        assert error is None

    def test_validate_string_invalid_type(self) -> None:
        """Test validation of string with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
        )
        is_valid, error = option.validate_value(123)
        assert is_valid is False
        assert error is not None and "must be text" in error

    def test_validate_string_too_long(self) -> None:
        """Test validation of string that is too long."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            max_length=5,
        )
        is_valid, error = option.validate_value("hello world")
        assert is_valid is False
        assert error is not None and "cannot exceed" in error

    def test_validate_integer_valid(self) -> None:
        """Test validation of valid integer."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            min_value=0,
            max_value=100,
        )
        is_valid, error = option.validate_value(50)
        assert is_valid is True
        assert error is None

    def test_validate_integer_invalid_type(self) -> None:
        """Test validation of integer with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
        )
        is_valid, error = option.validate_value("not a number")
        assert is_valid is False
        assert error is not None and "must be an integer" in error

    def test_validate_integer_below_min(self) -> None:
        """Test validation of integer below minimum."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            min_value=10,
        )
        is_valid, error = option.validate_value(5)
        assert is_valid is False
        assert error is not None and "must be at least" in error

    def test_validate_integer_above_max(self) -> None:
        """Test validation of integer above maximum."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            max_value=10,
        )
        is_valid, error = option.validate_value(15)
        assert is_valid is False
        assert error is not None and "cannot exceed" in error

    def test_validate_boolean_valid(self) -> None:
        """Test validation of valid boolean."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.BOOLEAN,
        )
        is_valid, error = option.validate_value(True)
        assert is_valid is True
        assert error is None

    def test_validate_boolean_invalid_type(self) -> None:
        """Test validation of boolean with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.BOOLEAN,
        )
        is_valid, error = option.validate_value("true")
        assert is_valid is False
        assert error is not None and "must be true or false" in error

    def test_validate_channel_valid(self) -> None:
        """Test validation of valid channel."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL,
        )
        is_valid, error = option.validate_value(123456789)
        assert is_valid is True
        assert error is None

    def test_validate_channel_invalid_type(self) -> None:
        """Test validation of channel with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL,
        )
        is_valid, error = option.validate_value("not an id")
        assert is_valid is False
        assert error is not None and "must be a valid ID" in error

    def test_validate_role_valid(self) -> None:
        """Test validation of valid role."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE,
        )
        is_valid, error = option.validate_value(123456789)
        assert is_valid is True
        assert error is None

    def test_validate_role_invalid_type(self) -> None:
        """Test validation of role with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE,
        )
        is_valid, error = option.validate_value("not an id")
        assert is_valid is False
        assert error is not None and "must be a valid ID" in error

    def test_validate_channel_list_valid(self) -> None:
        """Test validation of valid channel list."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL_LIST,
        )
        is_valid, error = option.validate_value([123, 456, 789])
        assert is_valid is True
        assert error is None

    def test_validate_channel_list_invalid(self) -> None:
        """Test validation of invalid channel list."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL_LIST,
        )
        is_valid, error = option.validate_value(["not", "ids"])
        assert is_valid is False
        assert error is not None and "must be a list of IDs" in error

    def test_validate_role_list_valid(self) -> None:
        """Test validation of valid role list."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE_LIST,
        )
        is_valid, error = option.validate_value([123, 456, 789])
        assert is_valid is True
        assert error is None

    def test_validate_role_list_invalid(self) -> None:
        """Test validation of invalid role list."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE_LIST,
        )
        is_valid, error = option.validate_value("not a list")
        assert is_valid is False
        assert error is not None and "must be a list of IDs" in error

    def test_validate_text_choice_valid(self) -> None:
        """Test validation of valid text choice."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[("Option A", "a"), ("Option B", "b")],
        )
        is_valid, error = option.validate_value("a")
        assert is_valid is True
        assert error is None

    def test_validate_text_choice_invalid(self) -> None:
        """Test validation of invalid text choice."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[("Option A", "a"), ("Option B", "b")],
        )
        is_valid, error = option.validate_value("c")
        assert is_valid is False
        assert error is not None and "must be one of the valid options" in error

    def test_validate_text_choice_no_choices(self) -> None:
        """Test validation of text choice without defined choices."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
        )
        is_valid, error = option.validate_value("anything")
        assert is_valid is True
        assert error is None

    def test_validate_textarea_valid(self) -> None:
        """Test validation of valid textarea."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=2000,
        )
        multiline_text = "Line 1\nLine 2\nLine 3"
        is_valid, error = option.validate_value(multiline_text)
        assert is_valid is True
        assert error is None

    def test_validate_textarea_with_markdown(self) -> None:
        """Test validation of textarea with Discord markdown."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=2000,
        )
        markdown_text = (
            "**Welcome**\n\n"
            "Please upload screenshots of:\n"
            "- :flag_es: Profile\n"
            "- <#123456789> Channel\n"
            "~~strikethrough~~ __underline__"
        )
        is_valid, error = option.validate_value(markdown_text)
        assert is_valid is True
        assert error is None

    def test_validate_textarea_invalid_type(self) -> None:
        """Test validation of textarea with invalid type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
        )
        is_valid, error = option.validate_value(123)
        assert is_valid is False
        assert error is not None and "must be text" in error

    def test_validate_textarea_too_long(self) -> None:
        """Test validation of textarea that is too long."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=100,
        )
        long_text = "a" * 150
        is_valid, error = option.validate_value(long_text)
        assert is_valid is False
        assert error is not None and "cannot exceed" in error

    def test_validate_table_valid(self) -> None:
        """Test validation of valid table."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role", "required": True},
                {"key": "tag", "name": "Tag", "type": "string", "required": True},
            ],
        )
        table_value = [
            {"role_id": 123, "tag": "CAP"},
            {"role_id": 456, "tag": "SGT"},
        ]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is True
        assert error is None

    def test_validate_table_not_list(self) -> None:
        """Test validation of table with non-list type."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        is_valid, error = option.validate_value("not a list")
        assert is_valid is False
        assert error is not None and "must be a list" in error

    def test_validate_table_row_not_dict(self) -> None:
        """Test validation of table with row that is not a dict."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        is_valid, error = option.validate_value(["not", "dicts"])
        assert is_valid is False
        assert error is not None and "must be an object" in error

    def test_validate_table_missing_required_column(self) -> None:
        """Test validation of table with missing required column."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role", "required": True},
                {"key": "tag", "name": "Tag", "type": "string", "required": True},
            ],
        )
        table_value = [
            {"role_id": 123},  # Missing "tag"
        ]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is False
        assert error is not None and "is required" in error

    def test_validate_table_empty_list(self) -> None:
        """Test validation of empty table (valid)."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Role", "type": "role", "required": True},
            ],
        )
        is_valid, error = option.validate_value([])
        assert is_valid is True
        assert error is None

    def test_validate_table_no_columns(self) -> None:
        """Test validation of table without defined columns."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        table_value = [{"any": "data"}]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is True
        assert error is None
