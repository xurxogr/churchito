"""Tests for StockpileCog."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.stockpile.cog import StockpileCog
from discord_bot.stockpile.config import COG_NAME, STOCKPILE_CONFIG_SCHEMA
from discord_bot.stockpile.enums import ConfigKey
from discord_bot.stockpile.service import StockpileService


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> Any:
    """Create mock of the bot with database."""
    bot: Any = MagicMock()
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.get_cog = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    bot.tree = MagicMock()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    bot.tree.sync = AsyncMock()
    return bot


@pytest.fixture
def stockpile_cog(mock_discord_bot: Any) -> StockpileCog:
    """Create cog instance for tests."""
    # Register schema so defaults are available
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(COG_NAME):
        schema_service.register_schema(STOCKPILE_CONFIG_SCHEMA)
    return StockpileCog(mock_discord_bot)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create mock of a guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    guild.get_channel = MagicMock(return_value=None)
    return guild


@pytest.fixture
def mock_role() -> MagicMock:
    """Create mock of a Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 100
    role.name = "TestRole"
    role.mention = "<@&100>"
    return role


@pytest.fixture
def mock_role2() -> MagicMock:
    """Create mock of a second Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 200
    role.name = "TestRole2"
    role.mention = "<@&200>"
    return role


@pytest.fixture
def mock_member(mock_guild: MagicMock, mock_role: MagicMock) -> MagicMock:
    """Create mock of a Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.bot = False
    member.display_name = "TestUser"
    member.mention = "<@111222333>"
    member.nick = None
    member.guild = mock_guild
    member.guild_permissions = MagicMock()
    member.guild_permissions.manage_guild = True
    member.roles = [mock_role]
    return member


@pytest.fixture
def mock_interaction(mock_guild: MagicMock, mock_member: MagicMock) -> MagicMock:
    """Create mock of a Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = mock_guild
    interaction.user = mock_member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.namespace = MagicMock()
    interaction.namespace.hex = None
    interaction.namespace.city = None
    return interaction


# ===== COG METHOD TESTS =====


class TestGetLockedOptions:
    """Tests for get_locked_options."""

    def test_returns_empty_dict(self, stockpile_cog: StockpileCog) -> None:
        """Test that returns empty dict."""
        result = stockpile_cog.get_locked_options()
        assert result == {}


class TestIsCogEnabled:
    """Tests for _is_cog_enabled."""

    async def test_cog_enabled(
        self, stockpile_cog: StockpileCog, test_database: DatabaseService
    ) -> None:
        """Test when cog is enabled."""
        guild_id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        result = await stockpile_cog._is_cog_enabled(guild_id)
        assert result is True

    async def test_cog_disabled(
        self, stockpile_cog: StockpileCog, test_database: DatabaseService
    ) -> None:
        """Test when cog is disabled."""
        guild_id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        result = await stockpile_cog._is_cog_enabled(guild_id)
        assert result is False


class TestGetConfig:
    """Tests for _get_config."""

    async def test_returns_config_dict(
        self, stockpile_cog: StockpileCog, test_database: DatabaseService
    ) -> None:
        """Test that returns a configuration dictionary."""
        guild_id = 123
        result = await stockpile_cog._get_config(guild_id)
        assert isinstance(result, dict)

    async def test_returns_saved_config(
        self, stockpile_cog: StockpileCog, test_database: DatabaseService
    ) -> None:
        """Test that returns saved configuration."""
        guild_id = 789

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100, 200],
            )
            await session.commit()

        result = await stockpile_cog._get_config(guild_id)
        assert result.get(ConfigKey.ADD_ROLES) == [100, 200]


class TestHasPermission:
    """Tests for _has_permission."""

    def test_has_permission_with_matching_role(
        self, stockpile_cog: StockpileCog, mock_member: MagicMock
    ) -> None:
        """Test when user has a matching role."""
        result = stockpile_cog._has_permission(member=mock_member, allowed_role_ids=[100])
        assert result is True

    def test_no_permission_without_matching_role(
        self, stockpile_cog: StockpileCog, mock_member: MagicMock
    ) -> None:
        """Test when user has no matching role."""
        result = stockpile_cog._has_permission(member=mock_member, allowed_role_ids=[999])
        assert result is False

    def test_no_permission_with_empty_list(
        self, stockpile_cog: StockpileCog, mock_member: MagicMock
    ) -> None:
        """Test when allowed roles list is empty."""
        result = stockpile_cog._has_permission(member=mock_member, allowed_role_ids=[])
        assert result is False


# ===== AUTOCOMPLETE TESTS =====


class TestHexAutocomplete:
    """Tests for hex_autocomplete."""

    async def test_returns_matching_hexes(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns matching hex choices."""
        result = await stockpile_cog.hex_autocomplete(mock_interaction, "Acr")
        assert len(result) >= 1
        assert any(c.name == "Acrithia" for c in result)

    async def test_returns_empty_for_no_match(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty list for no match."""
        result = await stockpile_cog.hex_autocomplete(mock_interaction, "XYZ123")
        assert len(result) == 0

    async def test_limits_to_25_choices(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that limits to 25 choices (Discord limit)."""
        result = await stockpile_cog.hex_autocomplete(mock_interaction, "")
        assert len(result) <= 25


class TestCityAutocomplete:
    """Tests for city_autocomplete."""

    async def test_returns_empty_without_hex(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when hex not selected."""
        mock_interaction.namespace.hex = None
        result = await stockpile_cog.city_autocomplete(mock_interaction, "")
        assert result == []

    async def test_returns_matching_cities(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns matching cities for selected hex."""
        mock_interaction.namespace.hex = "AcrithiaHex"
        result = await stockpile_cog.city_autocomplete(mock_interaction, "Pat")
        assert len(result) >= 1
        assert any(c.name == "Patridia" for c in result)

    async def test_returns_empty_for_invalid_hex(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty for invalid hex."""
        mock_interaction.namespace.hex = "InvalidHex"
        result = await stockpile_cog.city_autocomplete(mock_interaction, "")
        assert result == []


class TestStockpileNameAutocomplete:
    """Tests for stockpile_name_autocomplete."""

    async def test_returns_empty_without_guild(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when not in guild."""
        mock_interaction.guild = None
        result = await stockpile_cog.stockpile_name_autocomplete(mock_interaction, "")
        assert result == []

    async def test_returns_empty_without_hex(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when hex not selected."""
        mock_interaction.namespace.hex = None
        mock_interaction.namespace.city = "Patridia"
        result = await stockpile_cog.stockpile_name_autocomplete(mock_interaction, "")
        assert result == []

    async def test_returns_empty_without_city(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when city not selected."""
        mock_interaction.namespace.hex = "AcrithiaHex"
        mock_interaction.namespace.city = None
        result = await stockpile_cog.stockpile_name_autocomplete(mock_interaction, "")
        assert result == []

    async def test_returns_accessible_stockpile_names(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns names of accessible stockpiles."""
        guild_id = mock_interaction.guild.id
        mock_interaction.namespace.hex = "AcrithiaHex"
        mock_interaction.namespace.city = "Patridia"

        # Create a stockpile
        async with test_database.session() as session:
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="TestStock",
                code="123456",
                view_roles=[100],  # Role that mock_member has
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        result = await stockpile_cog.stockpile_name_autocomplete(mock_interaction, "")
        assert len(result) >= 1
        assert any(c.name == "TestStock" for c in result)

    async def test_returns_empty_when_user_not_member(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when user is not a Member (e.g., in DMs)."""
        mock_interaction.namespace.hex = "AcrithiaHex"
        mock_interaction.namespace.city = "Patridia"
        # Set user to a User instead of Member
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 12345
        mock_interaction.user = mock_user

        result = await stockpile_cog.stockpile_name_autocomplete(mock_interaction, "")
        assert result == []


# ===== COMMAND TESTS =====


class TestStockpileAddCommand:
    """Tests for stockpile_add command handler."""

    async def test_returns_when_not_in_guild(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test that returns early when not in guild."""
        mock_interaction.guild = None

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_when_cog_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns error when cog is disabled."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not enabled" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

    async def test_returns_when_no_permission(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns error when user lacks permission."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id,
                COG_NAME,
                ConfigKey.ADD_ROLES,
                [999],  # Role user doesn't have
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_validates_invalid_hex(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that validates hex location."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="InvalidHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "Invalid hex" in call_args[0][0]

    async def test_validates_invalid_city(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that validates city for hex."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="InvalidCity",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "Invalid city" in call_args[0][0]

    async def test_validates_name_length(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that validates name length."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="VeryLongName123",  # Too long
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "10 characters" in call_args[0][0]

    async def test_validates_code_format(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that validates code format."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="12345",  # Only 5 digits
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_prevents_duplicate_stockpile(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that prevents duplicate stockpile with same name (guild-wide)."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            # Create existing stockpile
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="Test",
                code="111111",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",  # Same name
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "already exists" in call_args[0][0]

    async def test_creates_stockpile_successfully(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that creates stockpile successfully."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="MyStock",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Should contain stockpile info
        assert "MyStock" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

        # Verify stockpile was created
        async with test_database.session() as session:
            service = StockpileService(session)
            stockpile = await service.get_by_location_and_name(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="MyStock",
            )
            assert stockpile is not None
            assert stockpile.code == "123456"

    async def test_returns_when_user_not_member(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns early when user is not a Member."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        # Set user to a User instead of Member
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 12345
        mock_interaction.user = mock_user

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_not_called()

    async def test_creates_stockpile_with_multiple_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that creates stockpile with optional role2 and role3."""
        guild_id = mock_interaction.guild.id

        # Create mock role3
        mock_role3 = MagicMock(spec=discord.Role)
        mock_role3.id = 300
        mock_role3.name = "TestRole3"
        mock_role3.mention = "<@&300>"

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        # Mock guild.get_role to return the correct role for each ID
        def get_role_by_id(role_id: int) -> MagicMock | None:
            roles = {100: mock_role, 200: mock_role2, 300: mock_role3}
            return roles.get(role_id)

        mock_interaction.guild.get_role = MagicMock(side_effect=get_role_by_id)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="MultiRole",
            code="123456",
            role1=str(mock_role.id),
            role2=str(mock_role2.id),
            role3=str(mock_role3.id),
        )

        mock_interaction.response.send_message.assert_called_once()

        # Verify stockpile was created with all roles
        async with test_database.session() as session:
            service = StockpileService(session)
            stockpile = await service.get_by_location_and_name(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="MultiRole",
            )
            assert stockpile is not None
            assert set(stockpile.view_roles) == {100, 200, 300}

    async def test_validates_role_against_allowed_view_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that validates role is in allowed_view_roles list."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            # Set allowed view roles - role 100 is NOT in the list
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.ALLOWED_VIEW_ROLES, [500, 600]
            )
            await session.commit()

        # Mock guild.get_role to return the role for conversion
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),  # Role 100 is not in allowed list
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True
        # Should show invalid roles message


class TestStockpileShowCommand:
    """Tests for stockpile_show command handler."""

    async def test_returns_when_not_in_guild(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns early when not in guild."""
        mock_interaction.guild = None

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_when_cog_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns error when cog is disabled."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not enabled" in call_args[0][0]

    async def test_shows_empty_message_when_no_stockpiles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that shows empty message when no stockpiles."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_shows_accessible_stockpiles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that shows accessible stockpiles as embeds."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Create stockpile visible to role 100
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="MyStock",
                code="123456",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Now sends embeds instead of text
        embeds = call_args.kwargs.get("embeds")
        assert embeds is not None
        assert len(embeds) == 1
        assert embeds[0].description is not None
        assert "MyStock" in embeds[0].description
        assert "123456" in embeds[0].description

    async def test_filters_by_hex(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that filters by hex."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="Stock1",
                code="111111",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await service.create(
                guild_id=guild_id,
                hex_key="AllodsBightHex",
                city="Homesick",
                name="Stock2",
                code="222222",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction, hex="AcrithiaHex")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Now sends embeds instead of text
        embeds = call_args.kwargs.get("embeds")
        assert embeds is not None
        assert len(embeds) == 1
        assert embeds[0].description is not None
        assert "Stock1" in embeds[0].description
        assert "Stock2" not in embeds[0].description

    async def test_returns_when_user_not_member(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns early when user is not a Member."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        # Set user to a User instead of Member
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 12345
        mock_interaction.user = mock_user

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_not_called()

    async def test_sends_one_embed_per_stockpile(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that sends one embed per stockpile."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Create a few stockpiles
            service = StockpileService(session)
            for i in range(5):
                await service.create(
                    guild_id=guild_id,
                    hex_key="AcrithiaHex",
                    city="Patridia",
                    name=f"Stock{i:03d}",
                    code=f"{i:06d}",
                    view_roles=[100],
                    created_by=111,
                    guild_name="Test Guild",
                )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        # Should send embeds
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args

        # Check that embeds were sent - one per stockpile
        embeds = call_args.kwargs.get("embeds")
        assert embeds is not None
        assert len(embeds) == 5  # One embed per stockpile

    async def test_sends_multiple_messages_when_many_stockpiles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that sends multiple messages when more than 10 embeds needed."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Create 15 stockpiles (exceeds 10 per message limit)
            service = StockpileService(session)
            for i in range(15):
                await service.create(
                    guild_id=guild_id,
                    hex_key="AcrithiaHex",
                    city="Patridia",
                    name=f"Stock{i:03d}",
                    code=f"{i:06d}",
                    view_roles=[100],
                    created_by=111,
                    guild_name="Test Guild",
                )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        # First batch sent via response (max 10 embeds)
        mock_interaction.response.send_message.assert_called_once()
        first_batch = mock_interaction.response.send_message.call_args.kwargs.get("embeds")
        assert first_batch is not None
        assert len(first_batch) == 10

        # Second batch sent via followup (remaining 5 embeds)
        mock_interaction.followup.send.assert_called_once()
        second_batch = mock_interaction.followup.send.call_args.kwargs.get("embeds")
        assert second_batch is not None
        assert len(second_batch) == 5


class TestStockpileDeleteCommand:
    """Tests for stockpile_delete command handler."""

    async def test_returns_when_not_in_guild(
        self, stockpile_cog: StockpileCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns early when not in guild."""
        mock_interaction.guild = None

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
        )

        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_when_cog_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns error when cog is disabled."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not enabled" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

    async def test_returns_when_user_not_member(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns early when user is not a Member."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        # Set user to a User instead of Member
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 12345
        mock_interaction.user = mock_user

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
        )

        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_when_no_permission(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns error when user lacks delete permission."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.DELETE_ROLES,
                value=[999],
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_returns_not_found_when_stockpile_missing(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns not found when stockpile doesn't exist."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.DELETE_ROLES,
                value=[100],
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="NonExistent",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Should indicate not found
        assert call_args[1]["ephemeral"] is True

    async def test_checks_view_permission_before_delete(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that verifies user can view stockpile before deleting."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.DELETE_ROLES,
                value=[100],
            )
            # Create stockpile visible only to role 999 (not user's role)
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="HiddenStock",
                code="123456",
                view_roles=[999],  # User doesn't have this role
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="HiddenStock",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Should deny permission (can't delete what you can't see)
        assert call_args[1]["ephemeral"] is True

        # Verify stockpile was NOT deleted
        async with test_database.session() as session:
            service = StockpileService(session)
            stockpile = await service.get_by_location_and_name(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="HiddenStock",
            )
            assert stockpile is not None

    async def test_deletes_stockpile_successfully(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that deletes stockpile successfully."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.DELETE_ROLES,
                value=[100],
            )
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="ToDelete",
                code="123456",
                view_roles=[100],  # User can view
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="ToDelete",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "ToDelete" in call_args[0][0]
        assert "deleted" in call_args[0][0].lower()

        # Verify stockpile was deleted
        async with test_database.session() as session:
            service = StockpileService(session)
            stockpile = await service.get_by_location_and_name(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="ToDelete",
            )
            assert stockpile is None

    async def test_handles_delete_returning_false(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test defensive handling when delete returns False unexpectedly."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.DELETE_ROLES,
                value=[100],
            )
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AcrithiaHex",
                city="Patridia",
                name="TestStock",
                code="123456",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        # Mock the delete method to return False
        with patch.object(StockpileService, "delete", new_callable=AsyncMock, return_value=False):
            await stockpile_cog._handle_stockpile_delete(
                mock_interaction,
                hex="AcrithiaHex",
                city="Patridia",
                name="TestStock",
            )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Should show not found message (defensive path)
        assert call_args[1]["ephemeral"] is True


# ===== SETUP/TEARDOWN TESTS =====


class TestSetupAndTeardown:
    """Tests for setup and teardown of the cog."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Test that setup registers the schema and adds the cog."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.stockpile.cog import setup

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        mock_discord_bot.add_cog.assert_called_once()
        # Verify that the schema was registered
        schema = get_config_schema_service().get_schema(COG_NAME)
        assert schema == STOCKPILE_CONFIG_SCHEMA

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Test that teardown unregisters the schema."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.stockpile.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()

        # First setup to register
        await setup(mock_discord_bot)
        assert get_config_schema_service().get_schema(COG_NAME) is not None

        # Then teardown
        await teardown(mock_discord_bot)
        assert get_config_schema_service().get_schema(COG_NAME) is None

    async def test_teardown_unregisters_commands(
        self, mock_discord_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """Test that teardown unregisters guild commands."""
        from discord_bot.stockpile.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        await setup(mock_discord_bot)

        # Get the cog and simulate registered commands
        cog = mock_discord_bot.add_cog.call_args[0][0]
        cog._registered_commands[mock_guild.id] = {"add": "cmd1", "show": "cmd2"}

        mock_discord_bot.get_cog = MagicMock(return_value=cog)

        await teardown(mock_discord_bot)

        # Should have called remove_command for each registered command
        assert mock_discord_bot.tree.remove_command.called


# ===== COMMAND REGISTRATION TESTS =====


class TestRegisterGuildCommands:
    """Tests for _register_guild_commands."""

    async def test_does_not_register_when_cog_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are not registered when cog is disabled."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await stockpile_cog._register_guild_commands(mock_guild)

        assert mock_guild.id not in stockpile_cog._registered_commands
        stockpile_cog.bot.tree.add_command.assert_not_called()  # type: ignore[attr-defined]

    async def test_unregisters_commands_when_cog_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are unregistered when cog becomes disabled."""
        guild_id = mock_guild.id

        # Simulate existing registered commands
        stockpile_cog._registered_commands[guild_id] = {"add": "old_add"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await stockpile_cog._register_guild_commands(mock_guild)

        assert guild_id not in stockpile_cog._registered_commands
        stockpile_cog.bot.tree.remove_command.assert_called()  # type: ignore[attr-defined]

    async def test_does_not_register_without_command_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are not registered without a command channel."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # No command channel set
            await session.commit()

        await stockpile_cog._register_guild_commands(mock_guild)

        assert guild_id not in stockpile_cog._registered_commands
        stockpile_cog.bot.tree.add_command.assert_not_called()  # type: ignore[attr-defined]

    async def test_registers_commands_with_channel_configured(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when channel is configured."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=999,
            )
            await session.commit()

        await stockpile_cog._register_guild_commands(mock_guild)

        assert guild_id in stockpile_cog._registered_commands
        assert stockpile_cog.bot.tree.add_command.call_count == 3  # type: ignore[attr-defined]


class TestRegisterCommand:
    """Tests for _register_command."""

    async def test_skips_if_already_registered(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that command is skipped if already registered with same name."""
        stockpile_cog._registered_commands[mock_guild.id] = {"add": "stockpile_add"}

        await stockpile_cog._register_command(mock_guild, "add", "stockpile_add", "Add stockpile")

        # Should not add or remove since name is same
        stockpile_cog.bot.tree.add_command.assert_not_called()  # type: ignore[attr-defined]
        stockpile_cog.bot.tree.remove_command.assert_not_called()  # type: ignore[attr-defined]

    async def test_removes_old_command_before_registering_new(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that old command is removed when name changes."""
        stockpile_cog._registered_commands[mock_guild.id] = {"add": "old_add_name"}

        await stockpile_cog._register_command(mock_guild, "add", "new_add_name", "Add stockpile")

        stockpile_cog.bot.tree.remove_command.assert_called_with(  # type: ignore[attr-defined]
            "old_add_name", guild=mock_guild
        )
        stockpile_cog.bot.tree.add_command.assert_called_once()  # type: ignore[attr-defined]

    async def test_registers_show_command(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test registration of show command."""
        stockpile_cog._registered_commands[mock_guild.id] = {}

        await stockpile_cog._register_command(
            mock_guild, "show", "stockpile_show", "Show stockpiles"
        )

        stockpile_cog.bot.tree.add_command.assert_called_once()  # type: ignore[attr-defined]
        assert stockpile_cog._registered_commands[mock_guild.id]["show"] == "stockpile_show"

    async def test_registers_delete_command(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test registration of delete command."""
        stockpile_cog._registered_commands[mock_guild.id] = {}

        await stockpile_cog._register_command(
            mock_guild, "delete", "stockpile_delete", "Delete stockpile"
        )

        stockpile_cog.bot.tree.add_command.assert_called_once()  # type: ignore[attr-defined]
        assert stockpile_cog._registered_commands[mock_guild.id]["delete"] == "stockpile_delete"

    async def test_ignores_unknown_command_key(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that unknown command keys are ignored."""
        stockpile_cog._registered_commands[mock_guild.id] = {}

        await stockpile_cog._register_command(
            mock_guild, "unknown", "some_name", "Some description"
        )

        stockpile_cog.bot.tree.add_command.assert_not_called()  # type: ignore[attr-defined]


class TestUnregisterGuildCommands:
    """Tests for _unregister_guild_commands."""

    async def test_removes_all_registered_commands(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that all commands are removed."""
        stockpile_cog._registered_commands[mock_guild.id] = {
            "add": "cmd_add",
            "show": "cmd_show",
            "delete": "cmd_delete",
        }

        await stockpile_cog._unregister_guild_commands(mock_guild)

        assert stockpile_cog.bot.tree.remove_command.call_count == 3  # type: ignore[attr-defined]
        assert mock_guild.id not in stockpile_cog._registered_commands

    async def test_handles_empty_registered_commands(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test handling when no commands registered."""
        # No commands registered for this guild
        await stockpile_cog._unregister_guild_commands(mock_guild)

        stockpile_cog.bot.tree.remove_command.assert_not_called()  # type: ignore[attr-defined]


class TestSyncGuildCommands:
    """Tests for _sync_guild_commands."""

    async def test_syncs_commands_successfully(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test successful command sync."""
        await stockpile_cog._sync_guild_commands(mock_guild)

        stockpile_cog.bot.tree.sync.assert_called_once_with(  # type: ignore[attr-defined]
            guild=mock_guild
        )

    async def test_handles_sync_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that sync errors are handled gracefully."""
        stockpile_cog.bot.tree.sync = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("Sync failed")
        )

        # Should not raise
        await stockpile_cog._sync_guild_commands(mock_guild)


# ===== EVENT LISTENER TESTS =====


class TestOnReady:
    """Tests for on_ready event listener."""

    async def test_registers_commands_for_all_guilds(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that on_ready registers commands for all guilds."""
        guild_id = mock_guild.id
        stockpile_cog.bot.guilds = [mock_guild]  # type: ignore[misc]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=999,
            )
            await session.commit()

        await stockpile_cog.on_ready()

        assert guild_id in stockpile_cog._registered_commands

    async def test_handles_registration_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that registration errors don't stop the process."""
        stockpile_cog.bot.guilds = [mock_guild]  # type: ignore[misc]

        # Mock _register_guild_commands to raise an exception
        with patch.object(
            stockpile_cog,
            "_register_guild_commands",
            new_callable=AsyncMock,
            side_effect=Exception("Registration error"),
        ):
            # Should not raise
            await stockpile_cog.on_ready()


class TestOnGuildJoin:
    """Tests for on_guild_join event listener."""

    async def test_registers_commands_on_join(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when bot joins a guild."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=999,
            )
            await session.commit()

        await stockpile_cog.on_guild_join(mock_guild)

        assert guild_id in stockpile_cog._registered_commands


# ===== CONFIG CHANGE CALLBACK TESTS =====


class TestOnConfigChanged:
    """Tests for on_config_changed callback."""

    async def test_reregisters_on_command_name_change(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are re-registered when name changes."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=999,
            )
            await session.commit()

        await stockpile_cog.on_config_changed(mock_guild, [ConfigKey.ADD_COMMAND_NAME])

        # Should have registered commands
        assert guild_id in stockpile_cog._registered_commands

    async def test_ignores_non_registration_keys(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that non-registration config keys don't trigger re-registration."""
        # Use a key that doesn't affect registration
        await stockpile_cog.on_config_changed(mock_guild, [ConfigKey.ADD_SUCCESS_TEXT])

        # Should not have called tree methods for re-registration
        stockpile_cog.bot.tree.add_command.assert_not_called()  # type: ignore[attr-defined]


class TestOnCogToggled:
    """Tests for on_cog_toggled callback."""

    async def test_registers_commands_when_enabled(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when cog is enabled."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=999,
            )
            await session.commit()

        await stockpile_cog.on_cog_toggled(mock_guild, enabled=True)

        assert guild_id in stockpile_cog._registered_commands

    async def test_unregisters_commands_when_disabled(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that commands are unregistered when cog is disabled."""
        guild_id = mock_guild.id
        stockpile_cog._registered_commands[guild_id] = {
            "add": "cmd_add",
            "show": "cmd_show",
        }

        await stockpile_cog.on_cog_toggled(mock_guild, enabled=False)

        assert guild_id not in stockpile_cog._registered_commands
        stockpile_cog.bot.tree.sync.assert_called()  # type: ignore[attr-defined]


# ===== CHANNEL CHECK TESTS =====


class TestCheckChannel:
    """Tests for _check_channel."""

    async def test_returns_true_when_no_channel_configured(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test returns True when no command channel is configured."""
        config: dict[str, Any] = {}  # No command channel

        result = await stockpile_cog._check_channel(mock_interaction, config)

        assert result is True
        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_true_when_correct_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test returns True when in correct channel."""
        mock_interaction.channel_id = 12345
        config = {ConfigKey.COMMAND_CHANNEL: 12345}

        result = await stockpile_cog._check_channel(mock_interaction, config)

        assert result is True
        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_false_and_sends_error_when_wrong_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test returns False and sends error when in wrong channel."""
        mock_interaction.channel_id = 99999
        mock_channel = MagicMock()
        mock_channel.mention = "<#12345>"
        mock_interaction.guild.get_channel = MagicMock(return_value=mock_channel)

        config = {ConfigKey.COMMAND_CHANNEL: 12345}

        result = await stockpile_cog._check_channel(mock_interaction, config)

        assert result is False
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_uses_fallback_mention_when_channel_not_found(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test uses fallback mention when channel can't be resolved."""
        mock_interaction.channel_id = 99999
        mock_interaction.guild.get_channel = MagicMock(return_value=None)

        config = {ConfigKey.COMMAND_CHANNEL: 12345}

        result = await stockpile_cog._check_channel(mock_interaction, config)

        assert result is False
        call_args = mock_interaction.response.send_message.call_args
        assert "<#12345>" in call_args[0][0]


# ===== NOTIFICATION TESTS =====


class TestSendAddNotification:
    """Tests for _send_add_notification."""

    async def test_does_nothing_without_channel_id(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test notification is not sent when no channel configured."""
        config: dict[str, Any] = {ConfigKey.ADD_NOTIFICATION_TEXT: "New stockpile!"}

        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )

        mock_guild.get_channel.assert_not_called()

    async def test_does_nothing_without_message_template(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test notification is not sent when no message template."""
        config = {ConfigKey.COMMAND_CHANNEL: 12345}

        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )

        mock_guild.get_channel.assert_not_called()

    async def test_sends_notification_successfully(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test notification is sent when properly configured."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        # Set up mock role mention
        mock_role.mention = "<@&100>"
        mock_member.mention = "<@111222333>"

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.ADD_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile {name} added at {hex}!"}],
            },
        }

        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="TestStock",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        embed = call_args.kwargs.get("embed")
        assert embed is not None
        # Check that placeholders were resolved in the field value
        assert embed.fields[0].value is not None
        assert "TestStock" in embed.fields[0].value
        assert "Acrithia" in embed.fields[0].value

    async def test_handles_channel_not_found(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test handles when notification channel doesn't exist."""
        mock_guild.get_channel = MagicMock(return_value=None)

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.ADD_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile added!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )

    async def test_handles_forbidden_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test handles Forbidden error when sending."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No permission"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        # Set up mock role mention
        mock_role.mention = "<@&100>"
        mock_member.mention = "<@111222333>"

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.ADD_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile added!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )

    async def test_handles_generic_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test handles generic errors when sending."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=Exception("Network error"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        # Set up mock role mention
        mock_role.mention = "<@&100>"
        mock_member.mention = "<@111222333>"

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.ADD_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile added!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_add_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            roles=[mock_role],
            creator=mock_member,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        )


class TestSendDeleteNotification:
    """Tests for _send_delete_notification."""

    async def test_does_nothing_without_channel_id(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
    ) -> None:
        """Test notification is not sent when no channel configured."""
        config: dict[str, Any] = {
            ConfigKey.DELETE_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile deleted!"}],
            }
        }

        await stockpile_cog._send_delete_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            view_role_ids=[100],
            created_by=999,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            deleted_by=mock_member,
        )

        mock_guild.get_channel.assert_not_called()

    async def test_sends_notification_successfully(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
    ) -> None:
        """Test delete notification is sent when properly configured."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.DELETE_NOTIFICATION_TEXT: {
                "sections": [
                    {"type": "text", "content": "Stockpile {name} deleted by {deleted_by}!"}
                ],
            },
        }

        await stockpile_cog._send_delete_notification(
            mock_guild,
            config,
            name="TestStock",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            view_role_ids=[100],
            created_by=999,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            deleted_by=mock_member,
        )

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        embed = call_args.kwargs.get("embed")
        assert embed is not None
        # Check that placeholders were resolved in the field value
        assert embed.fields[0].value is not None
        assert "TestStock" in embed.fields[0].value

    async def test_handles_forbidden_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
    ) -> None:
        """Test handles Forbidden error when sending."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No permission"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.DELETE_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile deleted!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_delete_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            view_role_ids=[100],
            created_by=999,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            deleted_by=mock_member,
        )

    async def test_handles_generic_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
    ) -> None:
        """Test handles generic errors when sending."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=Exception("Network error"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.DELETE_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile deleted!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_delete_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            view_role_ids=[100],
            created_by=999,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            deleted_by=mock_member,
        )


# ===== ROLE AUTOCOMPLETE TESTS =====


class TestGetAllowedRoles:
    """Tests for _get_allowed_roles."""

    async def test_returns_empty_when_no_allowed_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test returns empty list when no allowed roles configured."""
        # No ALLOWED_VIEW_ROLES configured
        result = await stockpile_cog._get_allowed_roles(mock_guild)

        assert result == []

    async def test_returns_filtered_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test returns roles from guild that are in allowed list."""
        guild_id = mock_guild.id

        def get_role_by_id(role_id: int) -> MagicMock | None:
            roles = {100: mock_role, 200: mock_role2}
            return roles.get(role_id)

        mock_guild.get_role = MagicMock(side_effect=get_role_by_id)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100, 200, 999],  # 999 doesn't exist
            )
            await session.commit()

        result = await stockpile_cog._get_allowed_roles(mock_guild)

        assert len(result) == 2
        assert mock_role in result
        assert mock_role2 in result

    async def test_excludes_specified_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test excludes roles in exclude set."""
        guild_id = mock_guild.id

        def get_role_by_id(role_id: int) -> MagicMock | None:
            roles = {100: mock_role, 200: mock_role2}
            return roles.get(role_id)

        mock_guild.get_role = MagicMock(side_effect=get_role_by_id)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100, 200],
            )
            await session.commit()

        result = await stockpile_cog._get_allowed_roles(mock_guild, exclude_role_ids={100})

        assert len(result) == 1
        assert mock_role2 in result


class TestRoleAutocomplete:
    """Tests for role autocomplete methods."""

    async def test_role1_autocomplete_returns_empty_without_guild(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test role1_autocomplete returns empty when no guild."""
        mock_interaction.guild = None

        result = await stockpile_cog.role1_autocomplete(mock_interaction, "")

        assert result == []

    async def test_role1_autocomplete_returns_matching_roles(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test role1_autocomplete returns matching allowed roles."""
        guild_id = mock_interaction.guild.id
        mock_interaction.guild.get_role = MagicMock(return_value=mock_role)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100],
            )
            await session.commit()

        result = await stockpile_cog.role1_autocomplete(mock_interaction, "Test")

        assert len(result) >= 1
        assert result[0].value == "100"

    async def test_role2_autocomplete_excludes_role1(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test role2_autocomplete excludes already selected role1."""
        guild_id = mock_interaction.guild.id
        mock_interaction.namespace.role1 = "100"  # role1 already selected

        def get_role_by_id(role_id: int) -> MagicMock | None:
            roles = {100: mock_role, 200: mock_role2}
            return roles.get(role_id)

        mock_interaction.guild.get_role = MagicMock(side_effect=get_role_by_id)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100, 200],
            )
            await session.commit()

        result = await stockpile_cog.role2_autocomplete(mock_interaction, "")

        # Should only return role2 since role1 is excluded
        assert len(result) == 1
        assert result[0].value == "200"

    async def test_role2_autocomplete_returns_empty_without_guild(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test role2_autocomplete returns empty when no guild."""
        mock_interaction.guild = None

        result = await stockpile_cog.role2_autocomplete(mock_interaction, "")

        assert result == []

    async def test_role3_autocomplete_excludes_role1_and_role2(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test role3_autocomplete excludes both role1 and role2."""
        guild_id = mock_interaction.guild.id
        mock_interaction.namespace.role1 = "100"
        mock_interaction.namespace.role2 = "200"

        mock_role3 = MagicMock(spec=discord.Role)
        mock_role3.id = 300
        mock_role3.name = "TestRole3"
        mock_role3.mention = "<@&300>"

        def get_role_by_id(role_id: int) -> MagicMock | None:
            roles = {100: mock_role, 200: mock_role2, 300: mock_role3}
            return roles.get(role_id)

        mock_interaction.guild.get_role = MagicMock(side_effect=get_role_by_id)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100, 200, 300],
            )
            await session.commit()

        result = await stockpile_cog.role3_autocomplete(mock_interaction, "")

        # Should only return role3 since role1 and role2 are excluded
        assert len(result) == 1
        assert result[0].value == "300"

    async def test_role3_autocomplete_returns_empty_without_guild(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test role3_autocomplete returns empty when no guild."""
        mock_interaction.guild = None

        result = await stockpile_cog.role3_autocomplete(mock_interaction, "")

        assert result == []

    async def test_role2_autocomplete_handles_invalid_role1(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test role2_autocomplete handles invalid role1 value."""
        guild_id = mock_interaction.guild.id
        mock_interaction.namespace.role1 = "not_a_number"

        mock_interaction.guild.get_role = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100],
            )
            await session.commit()

        # Should not raise
        result = await stockpile_cog.role2_autocomplete(mock_interaction, "")
        assert isinstance(result, list)

    async def test_role3_autocomplete_handles_invalid_role_values(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test role3_autocomplete handles invalid role1/role2 values."""
        guild_id = mock_interaction.guild.id
        mock_interaction.namespace.role1 = "not_a_number"
        mock_interaction.namespace.role2 = "also_invalid"

        mock_interaction.guild.get_role = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ALLOWED_VIEW_ROLES,
                value=[100],
            )
            await session.commit()

        # Should not raise
        result = await stockpile_cog.role3_autocomplete(mock_interaction, "")
        assert isinstance(result, list)


# ===== ADDITIONAL COMMAND HANDLER TESTS =====


class TestStockpileAddCommandChannelCheck:
    """Tests for channel checking in add command."""

    async def test_returns_error_when_wrong_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that error is returned when used in wrong channel."""
        guild_id = mock_interaction.guild.id
        mock_interaction.channel_id = 99999  # Wrong channel

        mock_channel = MagicMock()
        mock_channel.mention = "<#12345>"
        mock_interaction.guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,  # Correct channel is different
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1=str(mock_role.id),
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestStockpileAddRoleNotFound:
    """Tests for role handling in add command."""

    async def test_returns_error_when_role_not_found(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that error is returned when role doesn't exist."""
        guild_id = mock_interaction.guild.id

        # Mock get_role to return None (role not found)
        mock_interaction.guild.get_role = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1="999999",  # Role that doesn't exist
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "no longer exist" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True

    async def test_returns_error_when_role_id_invalid(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that error is returned when role ID is invalid."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.ADD_ROLES,
                value=[100],
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_add(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
            code="123456",
            role1="not_a_number",  # Invalid role ID
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "Invalid role" in call_args[0][0]
        assert call_args[1]["ephemeral"] is True


class TestRegisterGuildCommandsNoChannelWithExisting:
    """Test unregistering commands when channel is removed."""

    async def test_unregisters_when_channel_removed(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are unregistered when channel config is removed."""
        guild_id = mock_guild.id

        # Simulate existing registered commands
        stockpile_cog._registered_commands[guild_id] = {"add": "cmd_add"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # No command channel configured (removed)
            await session.commit()

        await stockpile_cog._register_guild_commands(mock_guild)

        assert guild_id not in stockpile_cog._registered_commands
        stockpile_cog.bot.tree.remove_command.assert_called()  # type: ignore[attr-defined]


class TestSendDeleteNotificationChannelNotFound:
    """Test delete notification with channel not found."""

    async def test_handles_channel_not_found(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
    ) -> None:
        """Test handles when notification channel doesn't exist."""
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_member.mention = "<@111222333>"

        config = {
            ConfigKey.COMMAND_CHANNEL: 12345,
            ConfigKey.DELETE_NOTIFICATION_TEXT: {
                "sections": [{"type": "text", "content": "Stockpile deleted!"}],
            },
        }

        # Should not raise
        await stockpile_cog._send_delete_notification(
            mock_guild,
            config,
            name="Test",
            hex_display="Acrithia",
            city="Patridia",
            code="123456",
            view_role_ids=[100],
            created_by=999,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            deleted_by=mock_member,
        )


class TestShowCommandWithHexFilter:
    """Tests for show command with hex filter and empty result."""

    async def test_shows_empty_message_with_hex_filter(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that shows empty message when no stockpiles match hex filter."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Create stockpile in different hex
            service = StockpileService(session)
            await service.create(
                guild_id=guild_id,
                hex_key="AllodsBightHex",
                city="Homesick",
                name="Stock1",
                code="111111",
                view_roles=[100],
                created_by=111,
                guild_name="Test Guild",
            )
            await session.commit()

        # Search for different hex (no results)
        await stockpile_cog._handle_stockpile_show(mock_interaction, hex="AcrithiaHex")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestDeleteCommandChannelCheck:
    """Test channel check in delete command."""

    async def test_returns_error_when_wrong_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that error is returned when used in wrong channel."""
        guild_id = mock_interaction.guild.id
        mock_interaction.channel_id = 99999  # Wrong channel

        mock_channel = MagicMock()
        mock_channel.mention = "<#12345>"
        mock_interaction.guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,  # Correct channel is different
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_delete(
            mock_interaction,
            hex="AcrithiaHex",
            city="Patridia",
            name="Test",
        )

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestShowCommandChannelCheck:
    """Test channel check in show command."""

    async def test_returns_error_when_wrong_channel(
        self,
        stockpile_cog: StockpileCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that error is returned when used in wrong channel."""
        guild_id = mock_interaction.guild.id
        mock_interaction.channel_id = 99999  # Wrong channel

        mock_channel = MagicMock()
        mock_channel.mention = "<#12345>"
        mock_interaction.guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,  # Correct channel is different
            )
            await session.commit()

        await stockpile_cog._handle_stockpile_show(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestUpdatePinnedMessage:
    """Tests for _update_pinned_message method."""

    async def test_does_nothing_when_templates_not_configured(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that nothing happens when pinned templates are not set."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Don't set pinned templates
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        # Should not try to send message
        mock_guild.get_channel.assert_not_called()

    async def test_does_nothing_when_no_channel_configured(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that nothing happens when channel is not configured."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            # Don't set channel
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        # Should not try to get channel (or if it does, it gets None)
        mock_guild.get_channel.assert_not_called()

    async def test_does_nothing_when_channel_not_found(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that nothing happens when channel doesn't exist."""
        guild_id = mock_guild.id
        mock_guild.get_channel.return_value = None

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        mock_guild.get_channel.assert_called_once_with(12345)

    async def test_sends_embed_message(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that embed message is sent."""
        guild_id = mock_guild.id

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 12345
        mock_channel.name = "stockpiles"
        mock_new_message = MagicMock()
        mock_new_message.id = 999888777
        mock_channel.send = AsyncMock(return_value=mock_new_message)
        mock_guild.get_channel.return_value = mock_channel

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex} - {city}** ({count})",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        # Should send embed
        mock_channel.send.assert_called_once()
        call_kwargs = mock_channel.send.call_args[1]
        assert "embed" in call_kwargs

    async def test_handles_forbidden_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden error is handled gracefully."""
        guild_id = mock_guild.id

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No permission"))
        mock_guild.get_channel.return_value = mock_channel

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            await session.commit()

        # Should not raise exception
        await stockpile_cog._update_pinned_message(mock_guild)

    async def test_handles_generic_error(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that generic errors are handled gracefully."""
        guild_id = mock_guild.id

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=Exception("Some error"))
        mock_guild.get_channel.return_value = mock_channel

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            await session.commit()

        # Should not raise exception
        await stockpile_cog._update_pinned_message(mock_guild)

    async def test_saves_message_id_after_send(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that message ID is saved after sending."""
        guild_id = mock_guild.id

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 12345
        mock_channel.name = "stockpiles"
        mock_new_message = MagicMock()
        mock_new_message.id = 999888777
        mock_channel.send = AsyncMock(return_value=mock_new_message)
        mock_guild.get_channel.return_value = mock_channel

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        # Check that message ID was saved
        async with test_database.session() as session:
            config_service = ConfigService(session)
            config = await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)
            assert config.get(ConfigKey.PINNED_MESSAGE_ID) == 999888777
            assert config.get(ConfigKey.PINNED_CHANNEL_ID) == 12345

    @patch("discord_bot.stockpile.cog.delete_message")
    async def test_deletes_old_message_before_creating_new(
        self,
        mock_delete_message: AsyncMock,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that old message is deleted before creating new one."""
        guild_id = mock_guild.id
        mock_delete_message.return_value = True

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 12345
        mock_channel.name = "stockpiles"
        mock_new_message = MagicMock()
        mock_new_message.id = 999888777
        mock_channel.send = AsyncMock(return_value=mock_new_message)
        mock_guild.get_channel.return_value = mock_channel

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_HEADER_TEXT,
                value="**{hex}**",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_ITEM_TEXT,
                value="{name}",
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_CHANNEL,
                value=12345,
            )
            # Set existing old message
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_MESSAGE_ID,
                value=111222333,
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_CHANNEL_ID,
                value=444555,
            )
            await session.commit()

        await stockpile_cog._update_pinned_message(mock_guild)

        # Should delete old message
        mock_delete_message.assert_called_once_with(mock_guild, 444555, 111222333)

        # Should send new message
        mock_channel.send.assert_called_once()


class TestDeletePinnedMessage:
    """Tests for _delete_pinned_message method."""

    async def test_does_nothing_when_no_message_saved(
        self,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that nothing happens when no message ID is saved."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            # Don't set message ID
            await session.commit()

        await stockpile_cog._delete_pinned_message(mock_guild)

        # Should not try to get channel
        mock_guild.get_channel.assert_not_called()

    @patch("discord_bot.stockpile.cog.delete_message")
    async def test_deletes_message_and_clears_config(
        self,
        mock_delete_message: AsyncMock,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that message is deleted and config is cleared."""
        guild_id = mock_guild.id
        mock_delete_message.return_value = True

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_MESSAGE_ID,
                value=123456,
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.PINNED_CHANNEL_ID,
                value=789,
            )
            await session.commit()

        await stockpile_cog._delete_pinned_message(mock_guild)

        # Should call delete_message
        mock_delete_message.assert_called_once_with(mock_guild, 789, 123456)

        # Check that config was cleared
        async with test_database.session() as session:
            config_service = ConfigService(session)
            config = await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)
            assert config.get(ConfigKey.PINNED_MESSAGE_ID) is None
            assert config.get(ConfigKey.PINNED_CHANNEL_ID) is None


class TestOnConfigChangedPinnedMessage:
    """Tests for on_config_changed with pinned message keys."""

    @patch.object(StockpileCog, "_update_pinned_message")
    async def test_updates_pinned_message_on_header_change(
        self,
        mock_update: AsyncMock,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that pinned message is updated when header template changes."""
        await stockpile_cog.on_config_changed(mock_guild, [ConfigKey.PINNED_HEADER_TEXT])

        mock_update.assert_called_once_with(mock_guild)

    @patch.object(StockpileCog, "_update_pinned_message")
    async def test_updates_pinned_message_on_item_change(
        self,
        mock_update: AsyncMock,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that pinned message is updated when item template changes."""
        await stockpile_cog.on_config_changed(mock_guild, [ConfigKey.PINNED_ITEM_TEXT])

        mock_update.assert_called_once_with(mock_guild)

    @patch.object(StockpileCog, "_update_pinned_message")
    @patch.object(StockpileCog, "_register_guild_commands")
    @patch.object(StockpileCog, "_sync_guild_commands")
    async def test_updates_pinned_message_on_channel_change(
        self,
        mock_sync: AsyncMock,
        mock_register: AsyncMock,
        mock_update: AsyncMock,
        stockpile_cog: StockpileCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that pinned message is updated when channel changes."""
        await stockpile_cog.on_config_changed(mock_guild, [ConfigKey.COMMAND_CHANNEL])

        # Channel change affects both commands and pinned message
        mock_register.assert_called_once()
        mock_update.assert_called_once_with(mock_guild)
