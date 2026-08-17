"""Tests for GuildScheduler."""

from datetime import UTC, datetime, timedelta

from discord_bot.common.utils.guild_scheduler import (
    DEFAULT_DISABLED_RECHECK_MINUTES,
    GuildScheduler,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_unknown_guild_is_due_immediately() -> None:
    """A guild that has never run is due on the first tick."""
    scheduler = GuildScheduler()

    assert scheduler.is_due(guild_id=1, now=NOW)
    assert scheduler.next_due(1) is None


def test_mark_run_defers_until_interval_elapses() -> None:
    """After a run the guild is not due until ``interval_minutes`` have passed."""
    scheduler = GuildScheduler()

    scheduler.mark_run(guild_id=1, now=NOW, interval_minutes=30)

    assert scheduler.next_due(1) == NOW + timedelta(minutes=30)
    assert not scheduler.is_due(guild_id=1, now=NOW + timedelta(minutes=29))
    assert scheduler.is_due(guild_id=1, now=NOW + timedelta(minutes=30))


def test_defer_uses_disabled_recheck_period() -> None:
    """A disabled guild is re-checked only after the configured recheck period."""
    scheduler = GuildScheduler(disabled_recheck_minutes=10)

    scheduler.defer(guild_id=1, now=NOW)

    assert not scheduler.is_due(guild_id=1, now=NOW + timedelta(minutes=9))
    assert scheduler.is_due(guild_id=1, now=NOW + timedelta(minutes=10))


def test_default_disabled_recheck_period() -> None:
    """Without an explicit period, ``defer`` uses the module default."""
    scheduler = GuildScheduler()

    scheduler.defer(guild_id=1, now=NOW)

    assert scheduler.next_due(1) == NOW + timedelta(minutes=DEFAULT_DISABLED_RECHECK_MINUTES)


def test_reset_makes_guild_due_on_next_tick() -> None:
    """Resetting forgets the schedule so a config change takes effect immediately."""
    scheduler = GuildScheduler()
    scheduler.mark_run(guild_id=1, now=NOW, interval_minutes=60)
    scheduler.mark_run(guild_id=2, now=NOW, interval_minutes=60)

    scheduler.reset(1)

    assert scheduler.is_due(guild_id=1, now=NOW)
    assert not scheduler.is_due(guild_id=2, now=NOW)
    scheduler.reset(999)  # unknown guilds are ignored
