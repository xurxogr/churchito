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

    Keys that come from an unbounded population (e.g. arbitrary user IDs)
    should set ``max_entries``: when the cache is full, expired entries are
    pruned and, if it is still full, the entry closest to expiry is evicted.
    """

    def __init__(self, ttl_seconds: float, max_entries: int | None = None) -> None:
        """Initialize an empty cache.

        Args:
            ttl_seconds (float): How long a value stays fresh after being loaded.
            max_entries (int | None): Upper bound on stored keys; ``None`` is unbounded.
        """
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[K, tuple[float, V]] = {}
        # Token of the latest in-flight load per key: a load only stores its
        # value if its token is still current, so an invalidate/clear issued
        # while the loader ran (e.g. the config changed from the dashboard)
        # is not overwritten by the stale value the loader read
        self._loads: dict[K, object] = {}

    def __len__(self) -> int:
        """Return the number of stored keys, including expired ones not yet reloaded.

        Returns:
            int: Number of stored entries.
        """
        return len(self._entries)

    def get(self, key: K, default: V | None = None) -> V | None:
        """Return the fresh value for a key, or ``default`` if absent or expired.

        Args:
            key (K): Cache key.
            default (V | None): Value returned on a miss.

        Returns:
            V | None: Cached value or the default.
        """
        entry = self._entries.get(key)
        if entry is not None and entry[0] > time.monotonic():
            return entry[1]
        return default

    def set(self, key: K, value: V) -> None:
        """Store a value for a key, starting a fresh TTL.

        Args:
            key (K): Cache key.
            value (V): Value to store.
        """
        self._store(key=key, value=value, now=time.monotonic())

    async def get_or_load(self, key: K, loader: Callable[[], Awaitable[V]]) -> V:
        """Return the cached value for a key, loading and storing it if stale or absent.

        Concurrent callers on a cold key may each run the loader; that is
        acceptable for the idempotent read-only loaders this cache is meant for,
        and only the most recently started load stores its value. A load whose
        key is invalidated while it runs returns its value without caching it.

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

        token = object()
        self._loads[key] = token
        try:
            value = await loader()
        finally:
            is_current = self._loads.get(key) is token
            if is_current:
                del self._loads[key]
        if is_current:
            self._store(key=key, value=value, now=now)
        return value

    def invalidate(self, key: K) -> None:
        """Drop a key so the next lookup reloads it.

        Args:
            key (K): Cache key; unknown keys are ignored.
        """
        self._entries.pop(key, None)
        self._loads.pop(key, None)

    def clear(self) -> None:
        """Drop every cached entry."""
        self._entries.clear()
        self._loads.clear()

    def _store(self, key: K, value: V, now: float) -> None:
        """Store an entry, making room first if the cache is bounded and full.

        Args:
            key (K): Cache key.
            value (V): Value to store.
            now (float): Current monotonic time.
        """
        if (
            self._max_entries is not None
            and key not in self._entries
            and len(self._entries) >= self._max_entries
        ):
            self._make_room(now=now)
        self._entries[key] = (now + self._ttl_seconds, value)

    def _make_room(self, now: float) -> None:
        """Prune expired entries; if none expired, evict the entry closest to expiry.

        Args:
            now (float): Current monotonic time.
        """
        expired = [k for k, (expires_at, _) in self._entries.items() if expires_at <= now]
        for k in expired:
            del self._entries[k]
        if expired or not self._entries:
            return
        oldest = min(self._entries, key=lambda k: self._entries[k][0])
        del self._entries[oldest]
