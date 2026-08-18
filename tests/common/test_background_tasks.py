"""Tests for the tracked fire-and-forget task helper."""

import asyncio
import logging

import pytest

from discord_bot.common.utils.background_tasks import BackgroundTasks


class TestBackgroundTasks:
    """Tests for BackgroundTasks."""

    async def test_spawn_runs_coroutine_and_forgets_it_when_done(self) -> None:
        """A spawned coroutine runs to completion and is dropped from the tracked set."""
        tasks = BackgroundTasks(logger=logging.getLogger("test"))
        done = asyncio.Event()

        async def work() -> None:
            done.set()

        tasks.spawn(work(), name="work")

        assert len(tasks) == 1
        await tasks.drain()
        assert done.is_set()
        assert len(tasks) == 0

    async def test_spawn_does_not_block_the_caller(self) -> None:
        """Spawn returns before the coroutine finishes."""
        tasks = BackgroundTasks(logger=logging.getLogger("test"))
        release = asyncio.Event()
        finished = False

        async def work() -> None:
            nonlocal finished
            await release.wait()
            finished = True

        tasks.spawn(work(), name="work")

        assert finished is False
        release.set()
        await tasks.drain()
        assert finished is True

    async def test_failure_is_logged_with_task_name(self, caplog: pytest.LogCaptureFixture) -> None:
        """An exception in a background task is logged, not raised, and does not stick around."""
        tasks = BackgroundTasks(logger=logging.getLogger("test.bg"))

        async def boom() -> None:
            raise RuntimeError("kaboom")

        with caplog.at_level(logging.ERROR, logger="test.bg"):
            tasks.spawn(boom(), name="autoname-sync-1")
            await tasks.drain()

        assert "autoname-sync-1" in caplog.text
        assert "kaboom" in caplog.text
        assert len(tasks) == 0

    async def test_cancel_all_cancels_pending_tasks_quietly(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """cancel_all stops running tasks and cancellation is not reported as an error."""
        tasks = BackgroundTasks(logger=logging.getLogger("test.bg"))

        async def forever() -> None:
            await asyncio.Event().wait()

        tasks.spawn(forever(), name="forever")
        with caplog.at_level(logging.ERROR, logger="test.bg"):
            tasks.cancel_all()
            await tasks.drain()

        assert len(tasks) == 0
        assert caplog.text == ""
