"""Tests for stockpile formatters and validation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from discord_bot.stockpile.formatters import (
    format_message,
    format_roles_list,
    format_stockpile_item,
    group_stockpiles_by_location,
    validate_code,
)


class TestFormatMessage:
    """Tests for format_message function."""

    def test_simple_replacement(self) -> None:
        """Test simple placeholder replacement."""
        result = format_message("Hello {name}!", name="World")
        assert result == "Hello World!"

    def test_multiple_replacements(self) -> None:
        """Test multiple placeholder replacements."""
        result = format_message(
            "{greeting} {name}, welcome to {place}!",
            greeting="Hello",
            name="User",
            place="Discord",
        )
        assert result == "Hello User, welcome to Discord!"

    def test_none_template(self) -> None:
        """Test with None template."""
        result = format_message(None)
        assert result == ""

    def test_empty_template(self) -> None:
        """Test with empty template."""
        result = format_message("")
        assert result == ""

    def test_none_value(self) -> None:
        """Test with None value."""
        result = format_message("Value: {value}", value=None)
        assert result == "Value: "

    def test_unknown_placeholder_unchanged(self) -> None:
        """Test that unknown placeholders are left unchanged."""
        result = format_message("Hello {name} and {unknown}!", name="World")
        assert result == "Hello World and {unknown}!"

    def test_integer_value(self) -> None:
        """Test with integer value."""
        result = format_message("Count: {count}", count=42)
        assert result == "Count: 42"


class TestFormatRolesList:
    """Tests for format_roles_list function."""

    def test_single_role(self) -> None:
        """Test with single role."""
        result = format_roles_list([123])
        assert result == "<@&123>"

    def test_multiple_roles(self) -> None:
        """Test with multiple roles."""
        result = format_roles_list([123, 456, 789])
        assert result == "<@&123>, <@&456>, <@&789>"

    def test_empty_roles(self) -> None:
        """Test with empty roles list."""
        result = format_roles_list([])
        assert result == "Everyone"


class TestFormatStockpileItem:
    """Tests for format_stockpile_item function."""

    def test_format_item(self) -> None:
        """Test formatting a stockpile item."""
        stockpile = MagicMock()
        stockpile.name = "TestStock"
        stockpile.code = "123456"
        stockpile.city = "Patridia"
        stockpile.view_roles = [111, 222]
        stockpile.created_by = 456
        stockpile.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        result = format_stockpile_item(
            stockpile=stockpile,
            template="**{name}**: `{code}` at {hex}/{city}",
            hex_display_name="Acrithia",
        )

        assert result == "**TestStock**: `123456` at Acrithia/Patridia"

    def test_format_item_with_roles(self) -> None:
        """Test formatting with roles placeholder."""
        stockpile = MagicMock()
        stockpile.name = "TestStock"
        stockpile.code = "123456"
        stockpile.city = "Patridia"
        stockpile.view_roles = [111]
        stockpile.created_by = 456
        stockpile.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        result = format_stockpile_item(
            stockpile=stockpile,
            template="{name} - Roles: {roles}",
            hex_display_name="Acrithia",
        )

        assert result == "TestStock - Roles: <@&111>"


class TestGroupStockpilesByLocation:
    """Tests for group_stockpiles_by_location function."""

    def test_group_by_location(self) -> None:
        """Test grouping stockpiles by location."""
        s1 = MagicMock()
        s1.hex_key = "AcrithiaHex"
        s1.city = "Patridia"

        s2 = MagicMock()
        s2.hex_key = "AcrithiaHex"
        s2.city = "Patridia"

        s3 = MagicMock()
        s3.hex_key = "AcrithiaHex"
        s3.city = "Swordfort"

        result = group_stockpiles_by_location([s1, s2, s3])

        assert len(result) == 2
        assert ("AcrithiaHex", "Patridia") in result
        assert ("AcrithiaHex", "Swordfort") in result
        assert len(result[("AcrithiaHex", "Patridia")]) == 2
        assert len(result[("AcrithiaHex", "Swordfort")]) == 1

    def test_group_empty_list(self) -> None:
        """Test grouping empty list."""
        result = group_stockpiles_by_location([])
        assert result == {}


class TestValidateCode:
    """Tests for validate_code function."""

    def test_valid_code(self) -> None:
        """Test valid 6-digit codes."""
        assert validate_code("123456") is True
        assert validate_code("000000") is True
        assert validate_code("999999") is True

    def test_invalid_code_too_short(self) -> None:
        """Test code that is too short."""
        assert validate_code("12345") is False
        assert validate_code("1") is False
        assert validate_code("") is False

    def test_invalid_code_too_long(self) -> None:
        """Test code that is too long."""
        assert validate_code("1234567") is False
        assert validate_code("12345678") is False

    def test_invalid_code_with_letters(self) -> None:
        """Test code with letters."""
        assert validate_code("12345a") is False
        assert validate_code("abcdef") is False

    def test_invalid_code_with_special_chars(self) -> None:
        """Test code with special characters."""
        assert validate_code("12345-") is False
        assert validate_code("123 456") is False
        assert validate_code("123.56") is False
