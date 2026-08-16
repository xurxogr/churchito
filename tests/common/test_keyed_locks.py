"""Tests for the KeyedLocks utility."""

import asyncio

import pytest

from discord_bot.common.utils.keyed_locks import KeyedLocks


@pytest.mark.asyncio
async def test_acquire_serializes_same_key() -> None:
    """Test that two tasks on the same key run one at a time."""
    locks = KeyedLocks()
    events: list[str] = []

    async def worker(name: str) -> None:
        async with locks.acquire(1):
            events.append(f"{name}-start")
            await asyncio.sleep(0)
            events.append(f"{name}-end")

    await asyncio.gather(worker("a"), worker("b"))

    assert events == ["a-start", "a-end", "b-start", "b-end"]


@pytest.mark.asyncio
async def test_acquire_does_not_block_other_keys() -> None:
    """Test that different keys can be held concurrently."""
    locks = KeyedLocks()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with locks.acquire(1):
            entered.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await entered.wait()

    async with locks.acquire(2):
        release.set()

    await task


@pytest.mark.asyncio
async def test_entry_evicted_after_release() -> None:
    """Test that a lock entry is removed once released."""
    locks = KeyedLocks()

    async with locks.acquire(1):
        assert len(locks) == 1

    assert len(locks) == 0


@pytest.mark.asyncio
async def test_entry_kept_while_contended() -> None:
    """Test that a contended entry survives until the last holder exits."""
    locks = KeyedLocks()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> None:
        async with locks.acquire(1):
            first_entered.set()
            await release_first.wait()

    async def second() -> None:
        async with locks.acquire(1):
            pass

    first_task = asyncio.create_task(first())
    await first_entered.wait()
    second_task = asyncio.create_task(second())
    await asyncio.sleep(0)

    assert len(locks) == 1

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert len(locks) == 0


@pytest.mark.asyncio
async def test_entry_evicted_after_exception() -> None:
    """Test that a lock entry is removed when the body raises."""
    locks = KeyedLocks()

    with pytest.raises(ValueError):
        async with locks.acquire(1):
            raise ValueError("boom")

    assert len(locks) == 0
