"""Per-guild "next due" bookkeeping for minute-tick background loops."""

from datetime import datetime, timedelta

DEFAULT_DISABLED_RECHECK_MINUTES = 10


class GuildScheduler:
    """Track when a periodic per-guild job is next due.

    Cogs run a ``tasks.loop(minutes=1)`` ticker and let each guild configure
    its own interval. Deciding whether a guild is due used to require
    reading its configuration on every tick, which meant a couple of
    database queries per guild per minute even when nothing was due. This
    remembers the next due time instead, so idle ticks touch nothing.

    Callers must ``reset`` a guild whenever its configuration changes
    (``on_config_changed``, ``on_cog_toggled``) so a new interval, or a
    re-enabled cog, is picked up on the next tick rather than when the old
    schedule expires. Guilds found disabled are re-checked after
    ``disabled_recheck_minutes`` as a safety net for changes that bypass
    those callbacks.
    """

    def __init__(self, disabled_recheck_minutes: int = DEFAULT_DISABLED_RECHECK_MINUTES) -> None:
        """Initialize an empty schedule.

        Args:
            disabled_recheck_minutes (int): How long ``defer`` postpones a disabled guild.
        """
        self._disabled_recheck = timedelta(minutes=disabled_recheck_minutes)
        self._next_due: dict[int, datetime] = {}

    def is_due(self, guild_id: int, now: datetime) -> bool:
        """Return whether the guild's job should run on this tick.

        Args:
            guild_id (int): Guild ID.
            now (datetime): Current time.

        Returns:
            bool: True if the guild has never run or its next due time has passed.
        """
        next_due = self._next_due.get(guild_id)
        return next_due is None or now >= next_due

    def next_due(self, guild_id: int) -> datetime | None:
        """Return when the guild is next due, or None if it is due immediately.

        Args:
            guild_id (int): Guild ID.

        Returns:
            datetime | None: Scheduled time, or None when unscheduled.
        """
        return self._next_due.get(guild_id)

    def mark_run(self, guild_id: int, now: datetime, interval_minutes: int) -> None:
        """Record a run and schedule the next one ``interval_minutes`` later.

        Args:
            guild_id (int): Guild ID.
            now (datetime): Time of the run.
            interval_minutes (int): Guild's configured interval in minutes.
        """
        self._next_due[guild_id] = now + timedelta(minutes=interval_minutes)

    def defer(self, guild_id: int, now: datetime) -> None:
        """Postpone a guild found disabled until the recheck period elapses.

        Args:
            guild_id (int): Guild ID.
            now (datetime): Current time.
        """
        self._next_due[guild_id] = now + self._disabled_recheck

    def reset(self, guild_id: int) -> None:
        """Forget the guild's schedule so it is due on the next tick.

        Args:
            guild_id (int): Guild ID; unknown guilds are ignored.
        """
        self._next_due.pop(guild_id, None)
