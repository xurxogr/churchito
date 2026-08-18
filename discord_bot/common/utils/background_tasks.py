"""Tracked fire-and-forget asyncio tasks.

``asyncio.create_task`` only keeps a weak reference to the task, so a
coroutine spawned and forgotten can be garbage collected mid-flight, and an
exception raised inside it is only reported when the task object is
destroyed. This helper keeps strong references until completion, logs
failures as soon as they happen and lets the owner cancel everything on
shutdown.
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any


class BackgroundTasks:
    """Own a set of fire-and-forget tasks and report their failures."""

    def __init__(self, *, logger: logging.Logger) -> None:
        """Initialize an empty task set.

        Args:
            logger (logging.Logger): Logger used to report failed tasks.
        """
        self._logger = logger
        self._tasks: set[asyncio.Task[None]] = set()

    def __len__(self) -> int:
        """Return the number of tasks still running.

        Returns:
            int: Number of tracked tasks.
        """
        return len(self._tasks)

    def spawn(self, coro: Coroutine[Any, Any, None], *, name: str) -> asyncio.Task[None]:
        """Run a coroutine in the background without blocking the caller.

        Args:
            coro (Coroutine[Any, Any, None]): Coroutine to run.
            name (str): Task name, used in the failure log line.

        Returns:
            asyncio.Task[None]: The scheduled task.
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished task and log its exception, if any.

        Args:
            task (asyncio.Task[None]): Task that just finished.
        """
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._logger.error(
                f"Background task '{task.get_name()}' failed: {error}", exc_info=error
            )

    def cancel_all(self) -> None:
        """Cancel every task that is still running."""
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

    async def drain(self) -> None:
        """Wait until every tracked task has finished (mainly for tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
