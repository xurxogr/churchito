"""Tests for the TTLCache utility."""

import asyncio
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
async def test_invalidate_during_load_does_not_cache_the_stale_value() -> None:
    """Test that a value loaded before an invalidation is not served afterwards."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    load_started = asyncio.Event()
    release_load = asyncio.Event()

    async def slow_loader() -> str:
        load_started.set()
        await release_load.wait()
        return "old"

    load_task = asyncio.create_task(cache.get_or_load(key=1, loader=slow_loader))
    await load_started.wait()
    cache.invalidate(key=1)
    release_load.set()

    assert await load_task == "old"
    assert cache.get(key=1) is None
    assert await cache.get_or_load(key=1, loader=AsyncMock(return_value="new")) == "new"


@pytest.mark.asyncio
async def test_clear_during_load_does_not_cache_the_stale_value() -> None:
    """Test that clear also discards values still being loaded."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    load_started = asyncio.Event()
    release_load = asyncio.Event()

    async def slow_loader() -> str:
        load_started.set()
        await release_load.wait()
        return "old"

    load_task = asyncio.create_task(cache.get_or_load(key=1, loader=slow_loader))
    await load_started.wait()
    cache.clear()
    release_load.set()

    assert await load_task == "old"
    assert cache.get(key=1) is None


@pytest.mark.asyncio
async def test_concurrent_loads_keep_the_latest_started_value() -> None:
    """Test that overlapping loads of a key end up caching the most recent read."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)
    release_first = asyncio.Event()

    async def first_loader() -> str:
        await release_first.wait()
        return "first"

    first_task = asyncio.create_task(cache.get_or_load(key=1, loader=first_loader))
    await asyncio.sleep(0)
    assert await cache.get_or_load(key=1, loader=AsyncMock(return_value="second")) == "second"
    release_first.set()

    assert await first_task == "first"
    assert cache.get(key=1) == "second"


@pytest.mark.asyncio
async def test_failed_load_does_not_block_a_later_load_from_caching() -> None:
    """Test that a loader error leaves no in-flight marker behind."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=60.0)

    with pytest.raises(RuntimeError):
        await cache.get_or_load(key=1, loader=AsyncMock(side_effect=RuntimeError("boom")))

    assert await cache.get_or_load(key=1, loader=AsyncMock(return_value="ok")) == "ok"
    assert cache.get(key=1) == "ok"


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


def test_get_returns_default_for_missing_or_expired_key() -> None:
    """Test that get() serves fresh values and falls back to the default otherwise."""
    cache: TTLCache[int, bool] = TTLCache(ttl_seconds=10.0)

    with patch(
        "discord_bot.common.utils.ttl_cache.time.monotonic",
        side_effect=[100.0, 105.0, 111.0],
    ):
        cache.set(key=1, value=True)
        assert cache.get(1) is True
        assert cache.get(1) is None

    assert cache.get(2, default=False) is False


def test_set_evicts_when_max_entries_is_reached() -> None:
    """Test that a bounded cache drops expired entries first, then the oldest one."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=10.0, max_entries=2)

    clock = patch(
        "discord_bot.common.utils.ttl_cache.time.monotonic",
        side_effect=[100.0, 101.0, 102.0, 102.0, 102.0, 103.0, 103.0, 103.0],
    )
    with clock:
        cache.set(key=1, value="a")  # expires at 110
        cache.set(key=2, value="b")  # expires at 111
        cache.set(key=3, value="c")  # full, nothing expired -> evicts key 1
        assert cache.get(1) is None
        assert cache.get(2) == "b"
        cache.set(key=4, value="d")  # still full -> evicts key 2 (oldest)
        assert cache.get(2) is None
        assert cache.get(3) == "c"

    assert len(cache) == 2


def test_set_prunes_expired_entries_before_evicting_fresh_ones() -> None:
    """Test that expired entries are dropped before any fresh one is evicted."""
    cache: TTLCache[int, str] = TTLCache(ttl_seconds=10.0, max_entries=2)

    clock = patch(
        "discord_bot.common.utils.ttl_cache.time.monotonic",
        side_effect=[100.0, 108.0, 112.0, 112.0, 112.0],
    )
    with clock:
        cache.set(key=1, value="a")  # expires at 110
        cache.set(key=2, value="b")  # expires at 118
        cache.set(key=3, value="c")  # key 1 expired -> pruned, key 2 survives
        assert cache.get(2) == "b"
        assert cache.get(3) == "c"
