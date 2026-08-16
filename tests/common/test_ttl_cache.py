"""Tests for the TTLCache utility."""

from unittest.mock import AsyncMock, patch

import pytest

from discord_bot.common.utils.ttl_cache import TTLCache


@pytest.mark.asyncio
async def test_get_or_load_calls_loader_once_within_ttl() -> None:
    """Test that a cached value is served without calling the loader again."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    loader = AsyncMock(return_value="value")

    first = await cache.get_or_load(key=1, loader=loader)
    second = await cache.get_or_load(key=1, loader=loader)

    assert first == "value"
    assert second == "value"
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_load_caches_none_values() -> None:
    """Test that None is a legitimate cached value, not a miss."""
    cache: TTLCache[int, str | None] = TTLCache(ttl_seconds=60.0)
    loader = AsyncMock(return_value=None)

    assert await cache.get_or_load(key=1, loader=loader) is None
    assert await cache.get_or_load(key=1, loader=loader) is None
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_load_reloads_after_expiry() -> None:
    """Test that the loader runs again once the TTL has elapsed."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=10.0)
    loader = AsyncMock(side_effect=["old", "new"])

    with patch(
        "discord_bot.common.utils.ttl_cache.time.monotonic",
        side_effect=[100.0, 105.0, 111.0, 111.0],
    ):
        assert await cache.get_or_load(key=1, loader=loader) == "old"
        assert await cache.get_or_load(key=1, loader=loader) == "old"
        assert await cache.get_or_load(key=1, loader=loader) == "new"

    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_keys_are_independent() -> None:
    """Test that different keys load and cache separately."""
    cache: TTLCache[int, int] = TTLCache(ttl_seconds=60.0)
    loader = AsyncMock(side_effect=[10, 20])

    assert await cache.get_or_load(key=1, loader=loader) == 10
    assert await cache.get_or_load(key=2, loader=loader) == 20
    assert await cache.get_or_load(key=1, loader=loader) == 10
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_invalidate_forces_reload_for_that_key_only() -> None:
    """Test that invalidate drops one key and leaves the rest cached."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    loader = AsyncMock(side_effect=["a1", "b1", "a2"])

    await cache.get_or_load(key=1, loader=loader)
    await cache.get_or_load(key=2, loader=loader)
    cache.invalidate(key=1)

    assert await cache.get_or_load(key=1, loader=loader) == "a2"
    assert await cache.get_or_load(key=2, loader=loader) == "b1"
    assert loader.await_count == 3


@pytest.mark.asyncio
async def test_invalidate_unknown_key_is_noop() -> None:
    """Test that invalidating a missing key does not raise."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)

    cache.invalidate(key=42)

    assert len(cache) == 0


@pytest.mark.asyncio
async def test_clear_drops_all_keys() -> None:
    """Test that clear empties the cache."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    loader = AsyncMock(return_value="v")

    await cache.get_or_load(key=1, loader=loader)
    await cache.get_or_load(key=2, loader=loader)
    assert len(cache) == 2

    cache.clear()

    assert len(cache) == 0
    await cache.get_or_load(key=1, loader=loader)
    assert loader.await_count == 3
