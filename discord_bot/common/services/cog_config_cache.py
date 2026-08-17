"""Per-guild cached snapshot of a cog's enabled flag and configuration."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.common.utils.ttl_cache import TTLCache

DEFAULT_CONFIG_CACHE_TTL_SECONDS = 60.0


class CogConfigSnapshot(BaseModel):
    """Enabled flag and full configuration of a cog for one guild.

    Attributes:
        enabled (bool): Whether the cog is enabled for the guild.
        config (dict[str, Any]): Configuration merged with schema defaults.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    config: dict[str, Any]


class CogConfigCache:
    """Cache a cog's per-guild enabled flag and configuration with a TTL.

    Cogs that react to high-frequency gateway events (member updates,
    reactions) previously opened one or two database sessions per event just
    to read configuration that rarely changes. This loads both values in a
    single session and serves them from memory until the TTL expires or the
    caller invalidates the guild after a known change (web dashboard
    callbacks, ``on_cog_toggled``, ``on_guild_remove``).
    """

    def __init__(
        self,
        database: DatabaseService,
        cog_name: str,
        ttl_seconds: float = DEFAULT_CONFIG_CACHE_TTL_SECONDS,
    ) -> None:
        """Initialize the cache.

        Args:
            database (DatabaseService): Database used to load snapshots.
            cog_name (str): Cog whose configuration is cached.
            ttl_seconds (float): How long a snapshot stays fresh.
        """
        self._database = database
        self._cog_name = cog_name
        self._cache: TTLCache[int, CogConfigSnapshot] = TTLCache(ttl_seconds=ttl_seconds)

    def __len__(self) -> int:
        """Return the number of guilds with a stored snapshot.

        Returns:
            int: Number of stored snapshots.
        """
        return len(self._cache)

    async def get(self, guild_id: int) -> CogConfigSnapshot:
        """Return the snapshot for a guild, loading it from the database if stale.

        Args:
            guild_id (int): Guild ID.

        Returns:
            CogConfigSnapshot: Enabled flag and configuration for the guild.
        """
        return await self._cache.get_or_load(key=guild_id, loader=lambda: self._load(guild_id))

    async def _load(self, guild_id: int) -> CogConfigSnapshot:
        """Read the enabled flag and configuration in a single session.

        Args:
            guild_id (int): Guild ID.

        Returns:
            CogConfigSnapshot: Freshly loaded snapshot.
        """
        async with self._database.session() as session:
            service = ConfigService(session=session)
            enabled = await service.is_cog_enabled(guild_id=guild_id, cog_name=self._cog_name)
            config = await service.get_all_config(guild_id=guild_id, cog_name=self._cog_name)
        return CogConfigSnapshot(enabled=enabled, config=config)

    def invalidate(self, guild_id: int) -> None:
        """Drop the snapshot for a guild so the next read reloads it.

        Args:
            guild_id (int): Guild ID.
        """
        self._cache.invalidate(guild_id)

    def clear(self) -> None:
        """Drop every cached snapshot."""
        self._cache.clear()
