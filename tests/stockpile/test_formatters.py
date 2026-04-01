"""Tests for stockpile formatters and validation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from discord_bot.stockpile.formatters import (
    format_message,
    format_pinned_message,
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

    def test_with_guild_resolves_names(self) -> None:
        """Test that roles are resolved to names when guild is provided."""
        guild = MagicMock()
        role1 = MagicMock()
        role1.name = "Admin"
        role2 = MagicMock()
        role2.name = "Member"
        guild.get_role.side_effect = lambda rid: {123: role1, 456: role2}.get(rid)

        result = format_roles_list([123, 456], guild=guild)
        assert result == "Admin, Member"

    def test_with_guild_handles_unknown_roles(self) -> None:
        """Test that unknown roles show as Unknown(id)."""
        guild = MagicMock()
        guild.get_role.return_value = None

        result = format_roles_list([999], guild=guild)
        assert result == "Unknown(999)"

    def test_with_guild_empty_roles(self) -> None:
        """Test empty roles with guild returns Everyone."""
        guild = MagicMock()
        result = format_roles_list([], guild=guild)
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


class TestFormatPinnedMessage:
    """Tests for format_pinned_message function."""

    def _create_stockpile(
        self,
        name: str,
        hex_key: str,
        city: str,
        code: str = "123456",
        view_roles: list[int] | None = None,
        created_by: int = 12345,
    ) -> MagicMock:
        """Helper to create mock stockpile."""
        stockpile = MagicMock()
        stockpile.name = name
        stockpile.hex_key = hex_key
        stockpile.city = city
        stockpile.code = code
        stockpile.view_roles = view_roles or []
        stockpile.created_by = created_by
        stockpile.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        return stockpile

    def test_empty_stockpiles(self) -> None:
        """Test with no stockpiles returns None."""
        guild = MagicMock()
        result = format_pinned_message(
            stockpiles=[],
            header_template="**{hex} - {city}** ({count})",
            item_template="**{name}** - `{code}`",
            guild=guild,
            hex_display_name_func=lambda x: x,
        )
        assert result is None

    def test_single_stockpile(self) -> None:
        """Test formatting single stockpile returns embed."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None

        stockpile = self._create_stockpile(
            name="Main",
            hex_key="AcrithiaHex",
            city="Patridia",
        )

        result = format_pinned_message(
            stockpiles=[stockpile],
            header_template="**{hex} - {city}** ({count})",
            item_template="**{name}**",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        assert "**Acrithia - Patridia** (1)" in result.description
        assert "**Main**" in result.description
        # Items should NOT have leading spaces (no nested bullets)
        assert "  **Main**" not in result.description

    def test_multiple_stockpiles_same_location(self) -> None:
        """Test formatting multiple stockpiles at same location."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None

        s1 = self._create_stockpile(name="Stock1", hex_key="AcrithiaHex", city="Patridia")
        s2 = self._create_stockpile(name="Stock2", hex_key="AcrithiaHex", city="Patridia")

        result = format_pinned_message(
            stockpiles=[s1, s2],
            header_template="**{hex} - {city}** ({count})",
            item_template="**{name}**",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        # Should have count of 2
        assert "**Acrithia - Patridia** (2)" in result.description
        assert "**Stock1**" in result.description
        assert "**Stock2**" in result.description

    def test_multiple_locations(self) -> None:
        """Test formatting stockpiles at different locations."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None

        s1 = self._create_stockpile(name="Stock1", hex_key="AcrithiaHex", city="Patridia")
        s2 = self._create_stockpile(name="Stock2", hex_key="AcrithiaHex", city="Swordfort")

        result = format_pinned_message(
            stockpiles=[s1, s2],
            header_template="**{hex} - {city}** ({count})",
            item_template="**{name}**",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        # Should have two location headers
        assert "**Acrithia - Patridia** (1)" in result.description
        assert "**Acrithia - Swordfort** (1)" in result.description

    def test_includes_all_placeholders(self) -> None:
        """Test that all placeholders are replaced with names (no mentions)."""
        guild = MagicMock()
        role = MagicMock()
        role.name = "Admin"
        guild.get_role.return_value = role

        member = MagicMock()
        member.display_name = "TestUser"
        guild.get_member.return_value = member

        stockpile = self._create_stockpile(
            name="Main",
            hex_key="AcrithiaHex",
            city="Patridia",
            code="654321",
            view_roles=[111],
            created_by=99999,
        )

        result = format_pinned_message(
            stockpiles=[stockpile],
            header_template="{hex} | {city} | {count}",
            item_template="{name} | {code} | {hex} | {city} | {roles} | {creator} | {created_at}",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        assert "Acrithia | Patridia | 1" in result.description
        # Creator should be display name, not ID or mention
        assert (
            "Main | 654321 | Acrithia | Patridia | Admin | TestUser | 2024-01-15 10:30"
            in result.description
        )

    def test_creator_fallback_when_member_not_found(self) -> None:
        """Test that creator shows Unknown(id) when member not in guild."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None  # Member left the guild

        stockpile = self._create_stockpile(
            name="Main",
            hex_key="AcrithiaHex",
            city="Patridia",
            created_by=99999,
        )

        result = format_pinned_message(
            stockpiles=[stockpile],
            header_template="{hex}",
            item_template="{name} by {creator}",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        assert "Main by Unknown(99999)" in result.description

    def test_created_at_relative_placeholder(self) -> None:
        """Test that created_at_relative uses Discord timestamp format."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None

        stockpile = self._create_stockpile(
            name="Main",
            hex_key="AcrithiaHex",
            city="Patridia",
        )
        # datetime(2024, 1, 15, 10, 30, tzinfo=UTC) -> 1705314600

        result = format_pinned_message(
            stockpiles=[stockpile],
            header_template="{hex}",
            item_template="{name} ({created_at_relative})",
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        # Should contain Discord relative timestamp format
        assert "<t:1705314600:R>" in result.description

    def test_truncates_long_description(self) -> None:
        """Test that descriptions over 4096 chars are truncated."""
        guild = MagicMock()
        guild.get_role.return_value = None
        guild.get_member.return_value = None

        # Create many stockpiles to exceed 4096 character limit
        stockpiles = []
        for i in range(100):
            stockpiles.append(
                self._create_stockpile(
                    name=f"VeryLongStockpileName_{i:03d}_WithExtraTextToMakeItEvenLonger",
                    hex_key="AcrithiaHex",
                    city="PatridiaWithAVeryLongCityNameThatAddsMoreCharacters",
                    code=f"{i:06d}",
                )
            )

        item_tpl = "**{name}**: `{code}` - {hex}/{city} - {roles} - {creator} - {created_at}"
        result = format_pinned_message(
            stockpiles=stockpiles,  # type: ignore[arg-type]
            header_template="**{hex} - {city}** ({count})",
            item_template=item_tpl,
            guild=guild,
            hex_display_name_func=lambda x: "Acrithia",
        )

        assert result is not None
        assert result.description is not None
        # Description should be truncated to 4096 characters
        assert len(result.description) <= 4096
        # Should end with "..." when truncated
        assert result.description.endswith("...")
