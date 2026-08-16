"""Small per-key cache with time-based expiry for hot event paths."""

import time
from collections.abc import Awaitable, Callable


class TTLCache[K, V]:
    """Cache values per key for a fixed time-to-live.

    Intended for per-guild configuration lookups on high-frequency Discord
    events (reactions, member updates), where opening a database session per
    event is the dominant cost. Callers invalidate keys explicitly when they
    know the underlying data changed; the TTL bounds staleness otherwise.

    ``None`` is a valid cached value: a miss is tracked by key absence, not by
    the stored value.
    """

    def __init__(self, ttl_seconds: float) -> None:
        """Initialize an empty cache.

        Args:
            ttl_seconds (float): How long a value stays fresh after being loaded.
        """
        self._ttl_seconds = ttl_seconds
        self._entries: dict[K, tuple[float, V]] = {}

    def __len__(self) -> int:
        """Return the number of stored keys, including expired ones not yet reloaded.

        Returns:
            int: Number of stored entries.
        """
        return len(self._entries)

    async def get_or_load(self, key: K, loader: Callable[[], Awaitable[V]]) -> V:
        """Return the cached value for a key, loading and storing it if stale or absent.

        Concurrent callers on a cold key may each run the loader; that is
        acceptable for the idempotent read-only loaders this cache is meant for.

        Args:
            key (K): Cache key.
            loader (Callable[[], Awaitable[V]]): Coroutine factory that produces the value.

        Returns:
            V: The cached or freshly loaded value.
        """
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]

        value = await loader()
        self._entries[key] = (now + self._ttl_seconds, value)
        return value

    def invalidate(self, key: K) -> None:
        """Drop a key so the next lookup reloads it.

        Args:
            key (K): Cache key; unknown keys are ignored.
        """
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Drop every cached entry."""
        self._entries.clear()
