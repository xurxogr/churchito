"""Tests for StockpileService."""

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.stockpile.service import StockpileService


class TestStockpileService:
    """Tests for StockpileService."""

    async def test_create_stockpile(self, test_session: AsyncSession) -> None:
        """Test stockpile creation."""
        service = StockpileService(test_session)

        stockpile = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[111, 222],
            created_by=456,
            guild_name="Test Guild",
        )

        assert stockpile.id is not None
        assert stockpile.public_id is not None
        assert stockpile.guild_id == 123
        assert stockpile.hex_key == "AcrithiaHex"
        assert stockpile.city == "Patridia"
        assert stockpile.name == "TestStock"
        assert stockpile.code == "123456"
        assert stockpile.view_roles == [111, 222]
        assert stockpile.created_by == 456

    async def test_get_by_id(self, test_session: AsyncSession) -> None:
        """Test getting stockpile by ID."""
        service = StockpileService(test_session)

        created = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        retrieved = await service.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "TestStock"

    async def test_get_by_id_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent stockpile."""
        service = StockpileService(test_session)
        result = await service.get_by_id(99999)
        assert result is None

    async def test_get_by_public_id(self, test_session: AsyncSession) -> None:
        """Test getting stockpile by public ID."""
        service = StockpileService(test_session)

        created = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        retrieved = await service.get_by_public_id(created.public_id)
        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_by_public_id_not_found(self, test_session: AsyncSession) -> None:
        """Test getting stockpile by non-existent public ID."""
        service = StockpileService(test_session)
        result = await service.get_by_public_id("nonexistent")
        assert result is None

    async def test_get_by_location_and_name(self, test_session: AsyncSession) -> None:
        """Test getting stockpile by location and name."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        found = await service.get_by_location_and_name(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
        )
        assert found is not None
        assert found.name == "TestStock"

    async def test_get_by_location_and_name_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent stockpile by location and name."""
        service = StockpileService(test_session)
        result = await service.get_by_location_and_name(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="NonExistent",
        )
        assert result is None

    async def test_get_all_for_guild(self, test_session: AsyncSession) -> None:
        """Test getting all stockpiles for a guild."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock1",
            code="111111",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Swordfort",
            name="Stock2",
            code="222222",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )
        await service.create(
            guild_id=999,  # Different guild
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock3",
            code="333333",
            view_roles=[],
            created_by=789,
            guild_name="Other Guild",
        )

        stockpiles = await service.get_all_for_guild(guild_id=123)
        assert len(stockpiles) == 2

    async def test_get_all_for_guild_with_hex_filter(self, test_session: AsyncSession) -> None:
        """Test getting stockpiles filtered by hex."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock1",
            code="111111",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )
        await service.create(
            guild_id=123,
            hex_key="AllodsBightHex",
            city="Homesick",
            name="Stock2",
            code="222222",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        stockpiles = await service.get_all_for_guild(guild_id=123, hex_key="AcrithiaHex")
        assert len(stockpiles) == 1
        assert stockpiles[0].hex_key == "AcrithiaHex"

    async def test_get_all_for_guild_with_city_filter(self, test_session: AsyncSession) -> None:
        """Test getting stockpiles filtered by hex and city."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock1",
            code="111111",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Swordfort",
            name="Stock2",
            code="222222",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        stockpiles = await service.get_all_for_guild(
            guild_id=123, hex_key="AcrithiaHex", city="Patridia"
        )
        assert len(stockpiles) == 1
        assert stockpiles[0].city == "Patridia"

    async def test_get_accessible_stockpiles(self, test_session: AsyncSession) -> None:
        """Test getting stockpiles accessible by user roles."""
        service = StockpileService(test_session)

        # Stockpile visible to role 111
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock1",
            code="111111",
            view_roles=[111],
            created_by=456,
            guild_name="Test Guild",
        )
        # Stockpile visible to role 222
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Swordfort",
            name="Stock2",
            code="222222",
            view_roles=[222],
            created_by=456,
            guild_name="Test Guild",
        )
        # Stockpile visible to everyone (no roles)
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Nereid Keep",
            name="Stock3",
            code="333333",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        # User with role 111 should see Stock1 and Stock3
        accessible = await service.get_accessible_stockpiles(guild_id=123, user_role_ids=[111])
        assert len(accessible) == 2
        names = {s.name for s in accessible}
        assert "Stock1" in names
        assert "Stock3" in names

    async def test_get_stockpile_names_at_location(self, test_session: AsyncSession) -> None:
        """Test getting stockpile names at a location."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock1",
            code="111111",
            view_roles=[111],
            created_by=456,
            guild_name="Test Guild",
        )
        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="Stock2",
            code="222222",
            view_roles=[222],
            created_by=456,
            guild_name="Test Guild",
        )

        # User with role 111 should only see Stock1
        names = await service.get_stockpile_names_at_location(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            user_role_ids=[111],
        )
        assert names == ["Stock1"]

    async def test_delete(self, test_session: AsyncSession) -> None:
        """Test deleting a stockpile."""
        service = StockpileService(test_session)

        stockpile = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        deleted = await service.delete(stockpile.id, "Test Guild")
        assert deleted is True

        # Verify it's gone
        result = await service.get_by_id(stockpile.id)
        assert result is None

    async def test_delete_not_found(self, test_session: AsyncSession) -> None:
        """Test deleting non-existent stockpile."""
        service = StockpileService(test_session)
        result = await service.delete(99999, "Test Guild")
        assert result is False

    async def test_delete_by_location_and_name(self, test_session: AsyncSession) -> None:
        """Test deleting stockpile by location and name."""
        service = StockpileService(test_session)

        await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],
            created_by=456,
            guild_name="Test Guild",
        )

        deleted = await service.delete_by_location_and_name(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            guild_name="Test Guild",
        )
        assert deleted is not None
        assert deleted.name == "TestStock"

        # Verify it's gone
        result = await service.get_by_location_and_name(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
        )
        assert result is None

    async def test_delete_by_location_and_name_not_found(self, test_session: AsyncSession) -> None:
        """Test deleting non-existent stockpile by location and name."""
        service = StockpileService(test_session)
        result = await service.delete_by_location_and_name(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="NonExistent",
            guild_name="Test Guild",
        )
        assert result is None


class TestStockpileModel:
    """Tests for Stockpile model methods."""

    async def test_can_view_with_matching_role(self, test_session: AsyncSession) -> None:
        """Test can_view returns True when user has a matching role."""
        service = StockpileService(test_session)

        stockpile = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[111, 222],
            created_by=456,
            guild_name="Test Guild",
        )

        assert stockpile.can_view([111]) is True
        assert stockpile.can_view([222]) is True
        assert stockpile.can_view([111, 333]) is True

    async def test_can_view_without_matching_role(self, test_session: AsyncSession) -> None:
        """Test can_view returns False when user has no matching role."""
        service = StockpileService(test_session)

        stockpile = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[111, 222],
            created_by=456,
            guild_name="Test Guild",
        )

        assert stockpile.can_view([333]) is False
        assert stockpile.can_view([]) is False

    async def test_can_view_with_no_roles_required(self, test_session: AsyncSession) -> None:
        """Test can_view returns True when no roles are required."""
        service = StockpileService(test_session)

        stockpile = await service.create(
            guild_id=123,
            hex_key="AcrithiaHex",
            city="Patridia",
            name="TestStock",
            code="123456",
            view_roles=[],  # No roles required
            created_by=456,
            guild_name="Test Guild",
        )

        assert stockpile.can_view([]) is True
        assert stockpile.can_view([111]) is True
