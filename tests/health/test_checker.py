"""Tests for discord_bot/health/checker.py."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_bot.health import checker as checker_module
from discord_bot.health.checker import HealthChecker


def _command(name: str) -> MagicMock:
    """Command stub with just a name.

    Args:
        name (str): Command name.

    Returns:
        MagicMock: Command mock.
    """
    command = MagicMock()
    command.name = name
    return command


def _guild(guild_id: int = 1, name: str = "Guild") -> MagicMock:
    """Guild stub.

    Args:
        guild_id (int): Guild ID.
        name (str): Guild name for log lines.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    return guild


@pytest.fixture
def bot() -> MagicMock:
    """Bot stub: one guild, every enabled extension loaded, tree in sync with Discord.

    Returns:
        MagicMock: Bot mock.
    """
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.settings.cogs.enabled_extensions.return_value = ("discord_bot.stockpile.cog",)
    bot.settings.health.interval_seconds = 0.01
    bot.extensions = {"discord_bot.stockpile.cog": object()}
    bot.load_extension = AsyncMock()
    bot.cogs = {}
    bot.guilds = [_guild()]
    bot.tree.get_commands.return_value = [_command("stockpile_mostrar")]
    bot.tree.fetch_commands = AsyncMock(return_value=[_command("stockpile_mostrar")])
    bot.tree.sync = AsyncMock()
    return bot


class TestExtensions:
    """Cogs enabled in the config must stay loaded."""

    async def test_missing_extension_is_loaded_again(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An enabled extension absent from the bot is reloaded and reported."""
        bot.extensions = {}

        with caplog.at_level(logging.WARNING):
            await HealthChecker(bot=bot).check_all()

        bot.load_extension.assert_awaited_once_with("discord_bot.stockpile.cog")
        assert "discord_bot.stockpile.cog" in caplog.text

    async def test_loaded_extensions_are_left_alone(self, bot: MagicMock) -> None:
        """Nothing is reloaded when every enabled extension is present."""
        await HealthChecker(bot=bot).check_all()

        bot.load_extension.assert_not_awaited()

    async def test_extension_load_failure_is_logged_not_raised(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing reload does not abort the rest of the check."""
        bot.extensions = {}
        bot.load_extension = AsyncMock(side_effect=RuntimeError("import boom"))

        with caplog.at_level(logging.ERROR):
            await HealthChecker(bot=bot).check_all()

        assert "import boom" in caplog.text
        bot.tree.fetch_commands.assert_awaited_once()


class TestCheckGuild:
    """Per-guild comparison between cogs, the local tree and Discord."""

    async def test_cogs_recover_their_commands_first(self, bot: MagicMock) -> None:
        """Cogs exposing recover_guild_commands are asked before Discord is consulted."""
        stockpile = MagicMock()
        stockpile.recover_guild_commands = AsyncMock(return_value=False)
        plain = MagicMock(spec=[])  # no recover_guild_commands attribute
        bot.cogs = {"StockpileCog": stockpile, "PlainCog": plain}
        guild = _guild()

        await HealthChecker(bot=bot).check_guild(guild)

        stockpile.recover_guild_commands.assert_awaited_once_with(guild=guild)

    async def test_in_sync_guild_is_not_touched(self, bot: MagicMock) -> None:
        """Same command names locally and on Discord means no sync."""
        repaired = await HealthChecker(bot=bot).check_guild(_guild())

        assert repaired is False
        bot.tree.sync.assert_not_awaited()

    async def test_mismatch_triggers_one_sync(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Discord holding a stale command and missing a local one is repaired with a sync."""
        bot.tree.get_commands.return_value = [_command("stockpile_mostrar"), _command("purgar")]
        bot.tree.fetch_commands = AsyncMock(
            return_value=[_command("stockpile_mostrar"), _command("viejo")]
        )
        guild = _guild()

        with caplog.at_level(logging.WARNING):
            repaired = await HealthChecker(bot=bot).check_guild(guild)

        assert repaired is True
        bot.tree.sync.assert_awaited_once_with(guild=guild)
        assert "purgar" in caplog.text and "viejo" in caplog.text

    async def test_repair_is_not_repeated_within_cooldown(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A guild still out of sync right after a repair is reported, not synced again."""
        bot.tree.fetch_commands = AsyncMock(return_value=[])
        guild = _guild()
        checker = HealthChecker(bot=bot)

        assert await checker.check_guild(guild) is True
        with caplog.at_level(logging.ERROR):
            assert await checker.check_guild(guild) is False

        bot.tree.sync.assert_awaited_once()
        assert "still" in caplog.text.lower()

    async def test_repair_allowed_again_after_cooldown(
        self, bot: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once the cooldown passed a persisting mismatch gets another repair."""
        monkeypatch.setattr(checker_module, "REPAIR_COOLDOWN", 0.0)
        bot.tree.fetch_commands = AsyncMock(return_value=[])
        guild = _guild()
        checker = HealthChecker(bot=bot)

        await checker.check_guild(guild)
        await checker.check_guild(guild)

        assert bot.tree.sync.await_count == 2

    async def test_successful_repair_clears_the_cooldown(self, bot: MagicMock) -> None:
        """A guild found in sync after a repair may be repaired again later without waiting."""
        bot.tree.fetch_commands = AsyncMock(side_effect=[[], [_command("stockpile_mostrar")], []])
        guild = _guild()
        checker = HealthChecker(bot=bot)

        assert await checker.check_guild(guild) is True
        assert await checker.check_guild(guild) is False
        assert await checker.check_guild(guild) is True

        assert bot.tree.sync.await_count == 2

    async def test_fetch_failure_is_logged_not_raised(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A Discord error while fetching leaves the guild alone and logs it."""
        bot.tree.fetch_commands = AsyncMock(side_effect=RuntimeError("Missing Access"))

        with caplog.at_level(logging.ERROR):
            repaired = await HealthChecker(bot=bot).check_guild(_guild())

        assert repaired is False
        bot.tree.sync.assert_not_awaited()
        assert "Missing Access" in caplog.text

    async def test_sync_failure_is_swallowed(self, bot: MagicMock) -> None:
        """A rejected repair sync is already logged by the sync helper and does not propagate."""
        bot.tree.fetch_commands = AsyncMock(return_value=[])
        bot.tree.sync = AsyncMock(side_effect=RuntimeError("rate limited"))

        repaired = await HealthChecker(bot=bot).check_guild(_guild())

        assert repaired is True


class TestCheckAll:
    """The whole-bot pass."""

    async def test_skips_when_bot_not_ready(self, bot: MagicMock) -> None:
        """Before the gateway is ready there is nothing trustworthy to compare."""
        bot.is_ready.return_value = False
        bot.extensions = {}

        await HealthChecker(bot=bot).check_all()

        bot.load_extension.assert_not_awaited()
        bot.tree.fetch_commands.assert_not_awaited()

    async def test_clean_pass_logs_a_summary(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A pass that finds nothing wrong still leaves one info line, so it is visibly running."""
        bot.guilds = [_guild(guild_id=1), _guild(guild_id=2)]

        with caplog.at_level(logging.INFO):
            await HealthChecker(bot=bot).check_all()

        summaries = [r for r in caplog.records if "Health check done" in r.getMessage()]
        assert len(summaries) == 1
        assert summaries[0].levelno == logging.INFO
        assert "2 guilds" in summaries[0].getMessage()
        assert "0 repaired" in summaries[0].getMessage()
        assert "0 failed" in summaries[0].getMessage()

    async def test_summary_counts_repairs_and_failures(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Repaired and failed guilds show up in the summary counts."""
        bot.guilds = [_guild(guild_id=1), _guild(guild_id=2), _guild(guild_id=3)]
        bot.tree.get_commands.side_effect = [
            [_command("x")],
            [_command("x"), _command("new")],
            RuntimeError("boom"),
        ]
        bot.tree.fetch_commands = AsyncMock(return_value=[_command("x")])

        with caplog.at_level(logging.INFO):
            await HealthChecker(bot=bot).check_all()

        messages = [r.getMessage() for r in caplog.records]
        summary = next(m for m in messages if "Health check done" in m)
        assert "3 guilds" in summary and "1 repaired" in summary and "1 failed" in summary

    async def test_one_failing_guild_does_not_stop_the_others(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Every guild is checked even if one raises unexpectedly."""
        bot.guilds = [_guild(guild_id=1, name="First"), _guild(guild_id=2, name="Second")]
        bot.tree.get_commands.side_effect = [RuntimeError("boom"), [_command("x")]]
        bot.tree.fetch_commands = AsyncMock(return_value=[_command("x")])

        with caplog.at_level(logging.ERROR):
            await HealthChecker(bot=bot).check_all()

        assert bot.tree.fetch_commands.await_count == 1
        assert "First" in caplog.text and "boom" in caplog.text


class TestRun:
    """The periodic loop."""

    async def test_runs_on_the_configured_interval_until_cancelled(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The loop waits the interval, checks, and stops cleanly on cancellation."""
        checker = HealthChecker(bot=bot)
        checker.check_all = AsyncMock()

        with caplog.at_level(logging.INFO):
            task = asyncio.create_task(checker.run())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert checker.check_all.await_count >= 1
        assert "stopped" in caplog.text.lower()

    async def test_check_errors_do_not_kill_the_loop(
        self, bot: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unexpected error in one pass is logged and the next pass still runs."""
        checker = HealthChecker(bot=bot)
        checker.check_all = AsyncMock(side_effect=[RuntimeError("pass failed"), None, None])

        with caplog.at_level(logging.ERROR):
            task = asyncio.create_task(checker.run())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert checker.check_all.await_count >= 2
        assert "pass failed" in caplog.text
