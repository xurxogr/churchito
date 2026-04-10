"""Service for purge database operations."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.purge.enums import PurgeStatus, PurgeType
from discord_bot.purge.models import PurgeRecord, PurgeUserResult


class PurgeService:
    """Service for purge database operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the service.

        Args:
            session (AsyncSession): Database session.
        """
        self._session = session

    async def create_purge(
        self,
        guild_id: int,
        purge_type: PurgeType,
        initiated_by: int,
        config_snapshot: dict[str, Any],
        scheduled_for: datetime,
        expires_at: datetime | None = None,
    ) -> PurgeRecord:
        """Create a new purge record.

        Args:
            guild_id (int): Guild ID.
            purge_type (PurgeType): Purge type.
            initiated_by (int): ID of the user who initiated.
            config_snapshot (dict[str, Any]): Configuration snapshot.
            scheduled_for (datetime): Scheduled execution date.
            expires_at (datetime | None): Authorization expiration date.

        Returns:
            PurgeRecord: Created record.
        """
        record = PurgeRecord(
            guild_id=guild_id,
            purge_type=purge_type,
            status=PurgeStatus.PENDING,
            initiated_by=initiated_by,
            authorized_by=[initiated_by],  # Initiator counts as first authorization
            cancelled_by=[],
            confirmed_by=[],
            config_snapshot=config_snapshot,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_purge(self, purge_id: int) -> PurgeRecord | None:
        """Get a purge by ID.

        Args:
            purge_id (int): Purge ID.

        Returns:
            PurgeRecord | None: Record if exists.
        """
        result = await self._session.execute(select(PurgeRecord).where(PurgeRecord.id == purge_id))
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> PurgeRecord | None:
        """Get a purge by public_id.

        Args:
            public_id (str): Purge public ID (NanoID).

        Returns:
            PurgeRecord | None: Record if exists.
        """
        result = await self._session.execute(
            select(PurgeRecord).where(PurgeRecord.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_active_purge_for_update(self, guild_id: int) -> PurgeRecord | None:
        """Get the active purge of a guild with write lock.

        Uses SELECT FOR UPDATE to prevent race conditions when creating
        a new purge. Must be used within a transaction.

        Args:
            guild_id (int): Guild ID.

        Returns:
            PurgeRecord | None: Active purge if exists (locked for update).
        """
        result = await self._session.execute(
            select(PurgeRecord)
            .where(
                PurgeRecord.guild_id == guild_id,
                PurgeRecord.status.in_(
                    [PurgeStatus.PENDING, PurgeStatus.AUTHORIZED, PurgeStatus.CANCEL_PENDING]
                ),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_mod_message(self, purge_id: int, channel_id: int, message_id: int) -> None:
        """Update moderation message IDs.

        Args:
            purge_id (int): Purge ID.
            channel_id (int): Channel ID.
            message_id (int): Message ID.
        """
        await self._session.execute(
            update(PurgeRecord)
            .where(PurgeRecord.id == purge_id)
            .values(mod_channel_id=channel_id, mod_message_id=message_id)
        )
        await self._session.flush()

    async def update_user_message(self, purge_id: int, channel_id: int, message_id: int) -> None:
        """Update user message IDs.

        Args:
            purge_id (int): Purge ID.
            channel_id (int): Channel ID.
            message_id (int): Message ID.
        """
        await self._session.execute(
            update(PurgeRecord)
            .where(PurgeRecord.id == purge_id)
            .values(user_channel_id=channel_id, user_message_id=message_id)
        )
        await self._session.flush()

    async def _update_user_list(
        self,
        purge_id: int,
        field_name: str,
        user_id: int,
        add: bool = True,
    ) -> PurgeRecord | None:
        """Update a user list in the purge record.

        Args:
            purge_id (int): Purge ID.
            field_name (str): Field name (authorized_by, cancelled_by, confirmed_by).
            user_id (int): User ID.
            add (bool): True to add, False to remove.

        Returns:
            PurgeRecord | None: Updated record.
        """
        record = await self.get_purge(purge_id)
        if not record:
            return None

        current_list: list[int] = getattr(record, field_name)
        user_in_list = user_id in current_list

        if add and not user_in_list:
            new_list = list(current_list)
            new_list.append(user_id)
            setattr(record, field_name, new_list)
            await self._session.flush()
        elif not add and user_in_list:
            new_list = list(current_list)
            new_list.remove(user_id)
            setattr(record, field_name, new_list)
            await self._session.flush()

        return record

    async def add_authorization(self, purge_id: int, user_id: int) -> PurgeRecord | None:
        """Add an authorization to the purge.

        Args:
            purge_id (int): Purge ID.
            user_id (int): ID of the authorizing user.

        Returns:
            PurgeRecord | None: Updated record.
        """
        return await self._update_user_list(
            purge_id=purge_id, field_name="authorized_by", user_id=user_id, add=True
        )

    async def add_cancellation(self, purge_id: int, user_id: int) -> PurgeRecord | None:
        """Add a cancellation vote to the purge.

        Args:
            purge_id (int): Purge ID.
            user_id (int): ID of the user voting to cancel.

        Returns:
            PurgeRecord | None: Updated record.
        """
        return await self._update_user_list(
            purge_id=purge_id, field_name="cancelled_by", user_id=user_id, add=True
        )

    async def add_confirmation(self, purge_id: int, user_id: int) -> PurgeRecord | None:
        """Add a user confirmation.

        Args:
            purge_id (int): Purge ID.
            user_id (int): ID of the confirming user.

        Returns:
            PurgeRecord | None: Updated record.
        """
        return await self._update_user_list(
            purge_id=purge_id, field_name="confirmed_by", user_id=user_id, add=True
        )

    async def remove_confirmation(self, purge_id: int, user_id: int) -> PurgeRecord | None:
        """Remove a user confirmation.

        Args:
            purge_id (int): Purge ID.
            user_id (int): ID of the user withdrawing confirmation.

        Returns:
            PurgeRecord | None: Updated record.
        """
        return await self._update_user_list(
            purge_id=purge_id, field_name="confirmed_by", user_id=user_id, add=False
        )

    async def clear_cancellations(self, purge_id: int) -> PurgeRecord | None:
        """Clear all cancellation votes from a purge.

        Args:
            purge_id (int): Purge ID.

        Returns:
            PurgeRecord | None: Updated record.
        """
        record = await self.get_purge(purge_id)
        if not record:
            return None

        if record.cancelled_by:
            record.cancelled_by = []
            await self._session.flush()

        return record

    async def update_status(
        self,
        purge_id: int,
        status: PurgeStatus,
        execution_result: dict[str, Any] | None = None,
        scheduled_for: datetime | None = None,
    ) -> PurgeRecord | None:
        """Update purge status.

        Args:
            purge_id (int): Purge ID.
            status (PurgeStatus): New status.
            execution_result (dict[str, Any] | None): Execution result (optional).
            scheduled_for (datetime | None): New execution date (optional).

        Returns:
            PurgeRecord | None: Updated record.
        """
        record = await self.get_purge(purge_id)
        if not record:
            return None

        record.status = status

        if scheduled_for is not None:
            record.scheduled_for = scheduled_for

        if status == PurgeStatus.AUTHORIZED:
            record.authorized_at = datetime.now(UTC)
        elif status in (PurgeStatus.EXECUTED, PurgeStatus.FAILED):
            record.executed_at = datetime.now(UTC)
            if execution_result:
                record.execution_result = execution_result

        await self._session.flush()
        return record

    async def get_pending_purges(self) -> list[PurgeRecord]:
        """Get all purges pending authorization.

        Returns:
            list[PurgeRecord]: List of pending purges.
        """
        result = await self._session.execute(
            select(PurgeRecord).where(PurgeRecord.status == PurgeStatus.PENDING)
        )
        return list(result.scalars().all())

    async def get_authorized_purges(self) -> list[PurgeRecord]:
        """Get all authorized purges pending execution.

        Returns:
            list[PurgeRecord]: List of authorized purges.
        """
        result = await self._session.execute(
            select(PurgeRecord).where(PurgeRecord.status == PurgeStatus.AUTHORIZED)
        )
        return list(result.scalars().all())

    async def get_cancel_pending_purges(self) -> list[PurgeRecord]:
        """Get all purges with pending cancellation.

        Returns:
            list[PurgeRecord]: List of purges with pending cancellation.
        """
        result = await self._session.execute(
            select(PurgeRecord).where(PurgeRecord.status == PurgeStatus.CANCEL_PENDING)
        )
        return list(result.scalars().all())

    async def add_user_result(
        self,
        purge_id: int,
        user_id: int,
        action_type: str,
        roles_before: list[int],
        roles_after: list[int],
        in_affected_group: bool | None = None,
    ) -> PurgeUserResult:
        """Add a user result to the purge.

        Args:
            purge_id (int): Purge ID.
            user_id (int): User ID.
            action_type (str): Action type ("cleaned" or "promoted").
            roles_before (list[int]): Roles before purge.
            roles_after (list[int]): Roles after purge.
            in_affected_group (bool | None): If had an affected role (for promoted).

        Returns:
            PurgeUserResult: Created record.
        """
        result = PurgeUserResult(
            purge_id=purge_id,
            user_id=user_id,
            action_type=action_type,
            roles_before=roles_before,
            roles_after=roles_after,
            in_affected_group=in_affected_group,
        )
        self._session.add(result)
        await self._session.flush()
        return result
