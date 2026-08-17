"""Tests for SharedAsyncClient."""

import httpx
import pytest

from discord_bot.common.utils.shared_http_client import SharedAsyncClient


@pytest.mark.asyncio
async def test_client_is_created_lazily_and_reused() -> None:
    """The underlying httpx client is created on first use and shared afterwards."""
    shared = SharedAsyncClient(timeout=3.0, follow_redirects=True)
    assert not shared.is_open

    first = shared.client()
    second = shared.client()

    assert first is second
    assert isinstance(first, httpx.AsyncClient)
    assert first.follow_redirects is True
    assert shared.is_open
    await shared.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_and_a_new_client_is_created_next_time() -> None:
    """Closing releases the pool; the next use gets a fresh client."""
    shared = SharedAsyncClient()
    first = shared.client()

    await shared.aclose()

    assert first.is_closed
    assert not shared.is_open
    second = shared.client()
    assert second is not first
    assert not second.is_closed
    await shared.aclose()


@pytest.mark.asyncio
async def test_aclose_without_client_is_noop() -> None:
    """Closing before any use does nothing."""
    shared = SharedAsyncClient()

    await shared.aclose()

    assert not shared.is_open


@pytest.mark.asyncio
async def test_externally_closed_client_is_replaced() -> None:
    """If someone closes the client behind our back, a new one is created."""
    shared = SharedAsyncClient()
    first = shared.client()
    await first.aclose()

    second = shared.client()

    assert second is not first
    await shared.aclose()
