"""Lazily created, reusable ``httpx.AsyncClient`` for outbound HTTP calls."""

from typing import Any

import httpx


class SharedAsyncClient:
    """Own one ``httpx.AsyncClient`` and hand it out for the process lifetime.

    Creating a client per request throws away its connection pool, so every
    call pays a new TCP/TLS handshake. Modules that talk to an external
    service keep one instance of this at module level, use ``client()`` per
    request and call ``aclose()`` on cog unload. Per-request settings (such
    as timeouts) belong on the request, not on the shared client.
    """

    def __init__(self, **client_options: Any) -> None:
        """Remember the options used to build the client.

        Args:
            **client_options (Any): Keyword arguments forwarded to ``httpx.AsyncClient``.
        """
        self._client_options = client_options
        self._client: httpx.AsyncClient | None = None

    @property
    def is_open(self) -> bool:
        """Whether a usable client currently exists.

        Returns:
            bool: True if a client was created and not closed.
        """
        return self._client is not None and not self._client.is_closed

    def client(self) -> httpx.AsyncClient:
        """Return the shared client, creating it if missing or closed.

        Returns:
            httpx.AsyncClient: Shared client with a reusable connection pool.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(**self._client_options)
        return self._client

    async def aclose(self) -> None:
        """Close the shared client, if one was created."""
        client, self._client = self._client, None
        if client is not None and not client.is_closed:
            await client.aclose()
