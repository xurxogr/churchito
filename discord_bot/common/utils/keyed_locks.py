"""Per-key asyncio locks that evict themselves when no longer in use."""

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager


class KeyedLocks:
    """Serialize work per key without accumulating idle lock entries.

    Unlike a plain ``dict[int, asyncio.Lock]``, entries are reference-counted
    and removed as soon as the last holder releases the lock, so the mapping
    only ever contains keys with active or waiting holders.
    """

    def __init__(self) -> None:
        """Initialize an empty lock pool."""
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._holders: dict[Hashable, int] = {}

    def __len__(self) -> int:
        """Return the number of keys with active or waiting holders.

        Returns:
            int: Number of live lock entries.
        """
        return len(self._locks)

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        """Acquire the lock for a key, creating and later evicting it as needed.

        Args:
            key (Hashable): Key identifying the lock (e.g. a user ID or a request public ID).

        Yields:
            None: Control while the lock is held.
        """
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._holders[key] = self._holders.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            remaining = self._holders[key] - 1
            if remaining:
                self._holders[key] = remaining
            else:
                del self._holders[key]
                del self._locks[key]
