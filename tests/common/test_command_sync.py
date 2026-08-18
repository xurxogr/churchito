"""Tests for the guild command sync helper."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_bot.common.utils.command_sync import CommandSyncError, sync_guild_commands


def _guild() -> MagicMock:
    """Guild stub with a name for log lines.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock()
    guild.name = "Guild"
    return guild


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
