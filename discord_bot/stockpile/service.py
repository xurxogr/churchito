"""Service for stockpile operations."""

import logging
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.stockpile.models import Stockpile

logger = logging.getLogger(__name__)


class StockpileService:
    """Service for stockpile CRUD operations.

    Handles the creation, update, query, and deletion of stockpiles.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the stockpile service.

        Args:
            session (AsyncSession): Database session
        """
        self._session = session

    async def create(
        self,
        guild_id: int,
        hex_key: str,
        city: str,
        name: str,
        code: str,
        view_roles: list[int],
        created_by: int,
        guild_name: str,
    ) -> Stockpile:
        """Create a new stockpile.

        Args:
            guild_id (int): Guild ID
            hex_key (str): Internal hex key (e.g., "AcrithiaHex")
            city (str): City name
            name (str): Stockpile name (max 10 chars)
            code (str): 6-digit access code
            view_roles (list[int]): List of role IDs that can view
            created_by (int): User ID who created
            guild_name (str): Guild name for logging

        Returns:
            Stockpile: Created stockpile
        """
        stockpile = Stockpile(
            guild_id=guild_id,
            hex_key=hex_key,
            city=city,
            name=name,
            code=code,
            view_roles=view_roles,
            created_by=created_by,
        )
        self._session.add(stockpile)
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Stockpile created: {name} at {hex_key}/{city} (ID: {stockpile.id})"
        )
        return stockpile

    async def get_by_id(self, stockpile_id: int) -> Stockpile | None:
        """Get a stockpile by ID.

        Args:
            stockpile_id (int): Stockpile ID

        Returns:
            Stockpile | None: Stockpile or None if not found
        """
        result = await self._session.execute(select(Stockpile).where(Stockpile.id == stockpile_id))
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> Stockpile | None:
        """Get a stockpile by public_id.

        Args:
            public_id (str): Public stockpile ID (NanoID)

        Returns:
            Stockpile | None: Stockpile or None if not found
        """
        result = await self._session.execute(
            select(Stockpile).where(Stockpile.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_by_location_and_name(
        self,
        guild_id: int,
        hex_key: str,
        city: str,
        name: str,
    ) -> Stockpile | None:
        """Get a stockpile by location and name.

        Args:
            guild_id (int): Guild ID
            hex_key (str): Hex key
            city (str): City name
            name (str): Stockpile name

        Returns:
            Stockpile | None: Stockpile or None if not found
        """
        result = await self._session.execute(
            select(Stockpile).where(
                Stockpile.guild_id == guild_id,
                Stockpile.hex_key == hex_key,
                Stockpile.city == city,
                Stockpile.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_guild_and_name(
        self,
        guild_id: int,
        name: str,
    ) -> Stockpile | None:
        """Get a stockpile by guild and name (guild-wide uniqueness check).

        Args:
            guild_id (int): Guild ID
            name (str): Stockpile name

        Returns:
            Stockpile | None: Stockpile or None if not found
        """
        result = await self._session.execute(
            select(Stockpile).where(
                Stockpile.guild_id == guild_id,
                Stockpile.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_for_guild(
        self,
        guild_id: int,
        hex_key: str | None = None,
        city: str | None = None,
    ) -> Sequence[Stockpile]:
        """Get all stockpiles for a guild with optional filters.

        Args:
            guild_id (int): Guild ID
            hex_key (str | None): Optional hex key filter
            city (str | None): Optional city filter (requires hex_key)

        Returns:
            Sequence[Stockpile]: List of stockpiles
        """
        query = select(Stockpile).where(Stockpile.guild_id == guild_id)

        if hex_key is not None:
            query = query.where(Stockpile.hex_key == hex_key)
            if city is not None:
                query = query.where(Stockpile.city == city)

        query = query.order_by(Stockpile.hex_key, Stockpile.city, Stockpile.name)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_accessible_stockpiles(
        self,
        guild_id: int,
        user_role_ids: list[int],
        hex_key: str | None = None,
        city: str | None = None,
    ) -> list[Stockpile]:
        """Get stockpiles accessible by a user based on their roles.

        Args:
            guild_id (int): Guild ID
            user_role_ids (list[int]): List of role IDs the user has
            hex_key (str | None): Optional hex key filter
            city (str | None): Optional city filter

        Returns:
            list[Stockpile]: List of accessible stockpiles
        """
        all_stockpiles = await self.get_all_for_guild(guild_id, hex_key, city)
        return [s for s in all_stockpiles if s.can_view(user_role_ids)]

    async def get_stockpile_names_at_location(
        self,
        guild_id: int,
        hex_key: str,
        city: str,
        user_role_ids: list[int],
    ) -> list[str]:
        """Get names of accessible stockpiles at a location.

        Used for autocomplete in delete command.

        Args:
            guild_id (int): Guild ID
            hex_key (str): Hex key
            city (str): City name
            user_role_ids (list[int]): User's role IDs for filtering

        Returns:
            list[str]: List of stockpile names
        """
        stockpiles = await self.get_accessible_stockpiles(guild_id, user_role_ids, hex_key, city)
        return [s.name for s in stockpiles]

    async def delete(
        self,
        stockpile_id: int,
        guild_name: str,
    ) -> bool:
        """Delete a stockpile by ID.

        Args:
            stockpile_id (int): Stockpile ID
            guild_name (str): Guild name for logging

        Returns:
            bool: True if deleted, False if not found
        """
        stockpile = await self.get_by_id(stockpile_id)
        if not stockpile:
            return False

        await self._session.execute(delete(Stockpile).where(Stockpile.id == stockpile_id))
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Stockpile deleted: {stockpile.name} at "
            f"{stockpile.hex_key}/{stockpile.city} (ID: {stockpile_id})"
        )
        return True
