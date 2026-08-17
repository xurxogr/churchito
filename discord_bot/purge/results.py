"""Buffered persistence of per-user purge results.

A purge can touch thousands of members and every Discord role edit is
rate-limited, so an execution may run for a long time. Persisting each
result inside one long-lived session kept a write transaction open for the
whole purge (blocking every other writer on SQLite and losing all rows on a
crash). The buffer here accumulates results in memory and writes them in
short-lived sessions, one batch at a time.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from discord_bot.common.services.database import DatabaseService
from discord_bot.purge.models import PurgeUserResult

DEFAULT_RESULT_BATCH_SIZE = 50


class UserResultSink(Protocol):
    """Anything that can record the outcome of a purge action for one user.

    Satisfied by both ``PurgeService`` (writes immediately in the caller's
    session) and ``PurgeResultBuffer`` (batches into short sessions).
    """

    async def add_user_result(
        self,
        purge_id: int,
        user_id: int,
        action_type: str,
        roles_before: list[int],
        roles_after: list[int],
        in_affected_group: bool | None = None,
    ) -> object:
        """Record the result of a purge action for a user."""
        ...


class PendingUserResult(BaseModel):
    """A per-user result waiting to be written.

    Attributes:
        user_id (int): Discord user ID.
        action_type (str): "cleaned" or "promoted".
        roles_before (list[int]): Role IDs before the action.
        roles_after (list[int]): Role IDs after the action.
        in_affected_group (bool | None): Whether the user had an affected role.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: int
    action_type: str
    roles_before: list[int]
    roles_after: list[int]
    in_affected_group: bool | None = None


class PurgeResultBuffer:
    """Accumulate per-user purge results and persist them in batches."""

    def __init__(
        self,
        database: DatabaseService,
        purge_id: int,
        batch_size: int = DEFAULT_RESULT_BATCH_SIZE,
    ) -> None:
        """Initialize an empty buffer.

        Args:
            database (DatabaseService): Database used for the short write sessions.
            purge_id (int): Purge the results belong to.
            batch_size (int): Number of pending results that triggers a write.
        """
        self._database = database
        self._purge_id = purge_id
        self._batch_size = batch_size
        self._pending: list[PendingUserResult] = []

    def __len__(self) -> int:
        """Return the number of results not yet written.

        Returns:
            int: Pending result count.
        """
        return len(self._pending)

    async def add_user_result(
        self,
        purge_id: int,
        user_id: int,
        action_type: str,
        roles_before: list[int],
        roles_after: list[int],
        in_affected_group: bool | None = None,
    ) -> PendingUserResult:
        """Queue a result, writing the batch if it is now full.

        Args:
            purge_id (int): Purge ID; must match the buffer's purge.
            user_id (int): Discord user ID.
            action_type (str): "cleaned" or "promoted".
            roles_before (list[int]): Role IDs before the action.
            roles_after (list[int]): Role IDs after the action.
            in_affected_group (bool | None): Whether the user had an affected role.

        Returns:
            PendingUserResult: The queued entry.

        Raises:
            ValueError: If purge_id does not match the buffer's purge.
        """
        if purge_id != self._purge_id:
            raise ValueError(
                f"Result for purge {purge_id} added to buffer of purge {self._purge_id}"
            )

        entry = PendingUserResult(
            user_id=user_id,
            action_type=action_type,
            roles_before=list(roles_before),
            roles_after=list(roles_after),
            in_affected_group=in_affected_group,
        )
        self._pending.append(entry)
        if len(self._pending) >= self._batch_size:
            await self.flush()
        return entry

    async def flush(self) -> None:
        """Write every pending result in one short session and clear the buffer."""
        if not self._pending:
            return

        batch, self._pending = self._pending, []
        rows = [
            PurgeUserResult(
                purge_id=self._purge_id,
                user_id=entry.user_id,
                action_type=entry.action_type,
                roles_before=entry.roles_before,
                roles_after=entry.roles_after,
                in_affected_group=entry.in_affected_group,
            )
            for entry in batch
        ]
        async with self._database.session() as session:
            session.add_all(rows)
            await session.commit()
