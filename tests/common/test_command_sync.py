"""Tests for the guild command sync helper."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_bot.common.utils import command_sync
from discord_bot.common.utils.command_sync import CommandSyncError, sync_guild_commands


def _guild(guild_id: int = 1) -> MagicMock:
    """Guild stub with a name for log lines.

    Args:
        guild_id (int): Guild ID; requests are coalesced per ID.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock()
    guild.id = guild_id
    guild.name = "Guild"
    return guild


class TestCoalescing:
    """Overlapping requests for one guild share a single sync."""

    async def test_concurrent_requests_for_one_guild_sync_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Three cogs asking within the window produce one tree push, logged with every label."""
        tree = MagicMock()
        tree.sync = AsyncMock()
        guild = _guild()

        with caplog.at_level(logging.INFO):
            await asyncio.gather(
                sync_guild_commands(tree=tree, guild=guild, label="purge"),
                sync_guild_commands(tree=tree, guild=guild, label="stockpile"),
                sync_guild_commands(tree=tree, guild=guild, label="roles"),
            )

        tree.sync.assert_awaited_once_with(guild=guild)
        logged = caplog.text.lower()
        assert "purge" in logged and "stockpile" in logged and "roles" in logged

    async def test_different_guilds_sync_separately(self) -> None:
        """Coalescing is per guild: two guilds mean two pushes."""
        tree = MagicMock()
        tree.sync = AsyncMock()
        first, second = _guild(guild_id=1), _guild(guild_id=2)

        await asyncio.gather(
            sync_guild_commands(tree=tree, guild=first, label="purge"),
            sync_guild_commands(tree=tree, guild=second, label="purge"),
        )

        assert tree.sync.await_count == 2
        synced = {call.kwargs["guild"].id for call in tree.sync.await_args_list}
        assert synced == {1, 2}

    async def test_failure_reaches_every_waiter(self) -> None:
        """A rejected shared sync raises CommandSyncError in each coalesced caller."""
        tree = MagicMock()
        tree.sync = AsyncMock(side_effect=RuntimeError("Missing Access"))
        guild = _guild()

        results = await asyncio.gather(
            sync_guild_commands(tree=tree, guild=guild, label="purge"),
            sync_guild_commands(tree=tree, guild=guild, label="stockpile"),
            return_exceptions=True,
        )

        assert len(results) == 2
        assert all(isinstance(r, CommandSyncError) for r in results)
        tree.sync.assert_awaited_once()

    async def test_later_request_syncs_again(self) -> None:
        """Once a shared sync finished, the next request starts a new one."""
        tree = MagicMock()
        tree.sync = AsyncMock()
        guild = _guild()

        await sync_guild_commands(tree=tree, guild=guild, label="purge")
        await sync_guild_commands(tree=tree, guild=guild, label="stockpile")

        assert tree.sync.await_count == 2

    async def test_sync_waits_for_the_coalescing_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The push happens after the delay, so cogs registering meanwhile get included."""
        monkeypatch.setattr(command_sync, "SYNC_COALESCE_DELAY", 0.05)
        tree = MagicMock()
        tree.sync = AsyncMock()
        guild = _guild()

        task = asyncio.create_task(sync_guild_commands(tree=tree, guild=guild, label="purge"))
        await asyncio.sleep(0)
        tree.sync.assert_not_awaited()
        await task

        tree.sync.assert_awaited_once_with(guild=guild)


class TestSyncGuildCommands:
    """Tests for sync_guild_commands."""

    async def test_syncs_and_logs_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """A successful sync calls the tree once and logs at info level."""
        tree = MagicMock()
        tree.sync = AsyncMock()
        guild = _guild()

        with caplog.at_level(logging.INFO):
            await sync_guild_commands(tree=tree, guild=guild, label="stockpile")

        tree.sync.assert_awaited_once_with(guild=guild)
        assert "[Guild]" in caplog.text and "stockpile" in caplog.text.lower()

    async def test_failure_is_logged_and_raised_with_details(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A Discord error is logged and re-raised as CommandSyncError keeping the cause."""
        tree = MagicMock()
        tree.sync = AsyncMock(side_effect=RuntimeError("403 Forbidden: Missing Access"))

        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(CommandSyncError, match="Missing Access") as info,
        ):
            await sync_guild_commands(tree=tree, guild=_guild(), label="roles")

        assert "roles" in str(info.value)
        assert isinstance(info.value.__cause__, RuntimeError)
        assert "[Guild]" in caplog.text and "Missing Access" in caplog.text
