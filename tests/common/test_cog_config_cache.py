"""Tests for CogConfigCache."""

from unittest.mock import patch

from discord_bot.common.services.cog_config_cache import CogConfigCache, CogConfigSnapshot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService

COG_NAME = "autoname"
GUILD_ID = 424242


async def _store(db: DatabaseService, enabled: bool, tag_format: str | None = None) -> None:
    async with db.session() as session:
        service = ConfigService(session)
        await service.set_cog_enabled(guild_id=GUILD_ID, cog_name=COG_NAME, enabled=enabled)
        if tag_format is not None:
            await service.set_value(
                guild_id=GUILD_ID, cog_name=COG_NAME, key="tag_format", value=tag_format
            )
        await session.commit()


async def test_snapshot_reflects_enabled_flag_and_config(test_database: DatabaseService) -> None:
    """The snapshot exposes the stored enabled flag and configuration."""
    await _store(db=test_database, enabled=True, tag_format="[X | {tag}]")
    cache = CogConfigCache(database=test_database, cog_name=COG_NAME)

    snapshot = await cache.get(GUILD_ID)

    assert isinstance(snapshot, CogConfigSnapshot)
    assert snapshot.enabled is True
    assert snapshot.config["tag_format"] == "[X | {tag}]"


async def test_unknown_guild_is_disabled_with_empty_config(test_database: DatabaseService) -> None:
    """Guilds without any stored rows are disabled with an empty config."""
    cache = CogConfigCache(database=test_database, cog_name="no_such_cog")

    snapshot = await cache.get(GUILD_ID)

    assert snapshot.enabled is False
    assert snapshot.config == {}


async def test_repeated_reads_open_a_single_session(test_database: DatabaseService) -> None:
    """Reads within the TTL are served from memory."""
    await _store(db=test_database, enabled=True)
    cache = CogConfigCache(database=test_database, cog_name=COG_NAME)

    with patch.object(test_database, "session", wraps=test_database.session) as session_spy:
        first = await cache.get(GUILD_ID)
        second = await cache.get(GUILD_ID)

    assert session_spy.call_count == 1
    assert first == second


async def test_invalidate_reloads_fresh_values(test_database: DatabaseService) -> None:
    """Invalidating a guild forces the next read to hit the database."""
    await _store(db=test_database, enabled=False)
    cache = CogConfigCache(database=test_database, cog_name=COG_NAME)
    assert (await cache.get(GUILD_ID)).enabled is False

    await _store(db=test_database, enabled=True)
    assert (await cache.get(GUILD_ID)).enabled is False  # still cached

    cache.invalidate(GUILD_ID)

    assert (await cache.get(GUILD_ID)).enabled is True


async def test_clear_drops_every_guild(test_database: DatabaseService) -> None:
    """clear() empties the cache for all guilds."""
    await _store(db=test_database, enabled=True)
    cache = CogConfigCache(database=test_database, cog_name=COG_NAME)
    await cache.get(GUILD_ID)
    await cache.get(GUILD_ID + 1)
    assert len(cache) == 2

    cache.clear()

    assert len(cache) == 0
