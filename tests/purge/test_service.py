"""Tests for PurgeService."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.purge.enums import PurgeStatus, PurgeType
from discord_bot.purge.service import PurgeService


class TestPurgeService:
    """Tests for PurgeService."""

    async def test_create_purge(self, test_session: AsyncSession) -> None:
        """Test purge creation."""
        service = PurgeService(test_session)
        scheduled_for = datetime.now(UTC) + timedelta(days=3)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={"test": "config"},
            scheduled_for=scheduled_for,
        )

        assert record.id is not None
        assert record.guild_id == 123
        assert record.purge_type == PurgeType.WAR_END
        assert record.status == PurgeStatus.PENDING
        assert record.initiated_by == 456
        assert record.authorized_by == [456]  # Initiator auto-authorizes
        assert record.confirmed_by == []
        assert record.config_snapshot == {"test": "config"}
        assert record.scheduled_for == scheduled_for

    async def test_create_purge_with_expiration(self, test_session: AsyncSession) -> None:
        """Test purge creation with expiration."""
        service = PurgeService(test_session)
        scheduled_for = datetime.now(UTC) + timedelta(days=3)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=scheduled_for,
            expires_at=expires_at,
        )

        assert record.expires_at == expires_at

    async def test_get_purge(self, test_session: AsyncSession) -> None:
        """Test getting purge by ID."""
        service = PurgeService(test_session)

        created = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        retrieved = await service.get_purge(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.guild_id == 123

    async def test_get_purge_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent purge."""
        service = PurgeService(test_session)
        result = await service.get_purge(99999)
        assert result is None

    async def test_get_active_purge(self, test_session: AsyncSession) -> None:
        """Test getting active purge."""
        service = PurgeService(test_session)

        await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        active = await service.get_active_purge(123)
        assert active is not None
        assert active.status == PurgeStatus.PENDING

    async def test_get_active_purge_none(self, test_session: AsyncSession) -> None:
        """Test getting active purge when there is none."""
        service = PurgeService(test_session)
        active = await service.get_active_purge(123)
        assert active is None

    async def test_get_active_purge_ignores_completed(self, test_session: AsyncSession) -> None:
        """Test that get_active_purge ignores completed purges."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record.id, status=PurgeStatus.CANCELLED)

        active = await service.get_active_purge(123)
        assert active is None

    async def test_get_active_purge_for_update(self, test_session: AsyncSession) -> None:
        """Test getting active purge with lock."""
        service = PurgeService(test_session)

        await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Should work the same as get_active_purge but with lock
        active = await service.get_active_purge_for_update(123)
        assert active is not None
        assert active.status == PurgeStatus.PENDING

    async def test_get_active_purge_for_update_includes_cancel_pending(
        self, test_session: AsyncSession
    ) -> None:
        """Test that get_active_purge_for_update includes CANCEL_PENDING."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record.id, status=PurgeStatus.CANCEL_PENDING)

        active = await service.get_active_purge_for_update(123)
        assert active is not None
        assert active.status == PurgeStatus.CANCEL_PENDING

    async def test_update_mod_message(self, test_session: AsyncSession) -> None:
        """Test updating moderation message IDs."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.update_mod_message(purge_id=record.id, channel_id=111, message_id=222)

        updated = await service.get_purge(record.id)
        assert updated is not None
        assert updated.mod_channel_id == 111
        assert updated.mod_message_id == 222

    async def test_update_user_message(self, test_session: AsyncSession) -> None:
        """Test updating user message IDs."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.update_user_message(purge_id=record.id, channel_id=333, message_id=444)

        updated = await service.get_purge(record.id)
        assert updated is not None
        assert updated.user_channel_id == 333
        assert updated.user_message_id == 444

    async def test_add_authorization(self, test_session: AsyncSession) -> None:
        """Test adding authorization."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_authorization(purge_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.authorized_by
        assert len(updated.authorized_by) == 2  # Initiator + new

    async def test_add_authorization_duplicate(self, test_session: AsyncSession) -> None:
        """Test that authorizations are not duplicated."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_authorization(purge_id=record.id, user_id=456)
        updated = await service.get_purge(record.id)
        assert updated is not None
        assert updated.authorized_by.count(456) == 1

    async def test_add_authorization_not_found(self, test_session: AsyncSession) -> None:
        """Test adding authorization to non-existent purge."""
        service = PurgeService(test_session)
        result = await service.add_authorization(purge_id=99999, user_id=789)
        assert result is None

    async def test_add_confirmation(self, test_session: AsyncSession) -> None:
        """Test adding confirmation."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_confirmation(purge_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.confirmed_by

    async def test_add_confirmation_duplicate(self, test_session: AsyncSession) -> None:
        """Test that confirmations are not duplicated."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_confirmation(purge_id=record.id, user_id=789)
        await service.add_confirmation(purge_id=record.id, user_id=789)
        updated = await service.get_purge(record.id)
        assert updated is not None
        assert updated.confirmed_by.count(789) == 1

    async def test_remove_confirmation(self, test_session: AsyncSession) -> None:
        """Test removing confirmation."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.add_confirmation(purge_id=record.id, user_id=789)

        updated = await service.remove_confirmation(purge_id=record.id, user_id=789)
        assert updated is not None
        assert 789 not in updated.confirmed_by

    async def test_update_status_to_authorized(self, test_session: AsyncSession) -> None:
        """Test updating status to authorized."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.update_status(purge_id=record.id, status=PurgeStatus.AUTHORIZED)

        assert updated is not None
        assert updated.status == PurgeStatus.AUTHORIZED
        assert updated.authorized_at is not None

    async def test_update_status_to_executed(self, test_session: AsyncSession) -> None:
        """Test updating status to executed."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        execution_result = {"purged": 10, "promoted": 5}
        updated = await service.update_status(
            purge_id=record.id,
            status=PurgeStatus.EXECUTED,
            execution_result=execution_result,
        )

        assert updated is not None
        assert updated.status == PurgeStatus.EXECUTED
        assert updated.executed_at is not None
        assert updated.execution_result == execution_result

    async def test_update_status_not_found(self, test_session: AsyncSession) -> None:
        """Test updating status of non-existent purge."""
        service = PurgeService(test_session)
        result = await service.update_status(purge_id=99999, status=PurgeStatus.CANCELLED)
        assert result is None

    async def test_get_pending_purges(self, test_session: AsyncSession) -> None:
        """Test getting pending purges."""
        service = PurgeService(test_session)

        await service.create_purge(
            guild_id=111,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        record2 = await service.create_purge(
            guild_id=222,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record2.id, status=PurgeStatus.CANCELLED)

        pending = await service.get_pending_purges()
        assert len(pending) == 1
        assert pending[0].guild_id == 111

    async def test_get_authorized_purges(self, test_session: AsyncSession) -> None:
        """Test getting authorized purges."""
        service = PurgeService(test_session)

        await service.create_purge(
            guild_id=111,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        record2 = await service.create_purge(
            guild_id=222,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record2.id, status=PurgeStatus.AUTHORIZED)

        authorized = await service.get_authorized_purges()
        assert len(authorized) == 1
        assert authorized[0].guild_id == 222

    async def test_different_guilds_isolated(self, test_session: AsyncSession) -> None:
        """Test that different guilds have isolated data."""
        service = PurgeService(test_session)

        await service.create_purge(
            guild_id=111,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.create_purge(
            guild_id=222,
            purge_type=PurgeType.GLOBAL,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        active_111 = await service.get_active_purge(111)
        active_222 = await service.get_active_purge(222)

        assert active_111 is not None
        assert active_222 is not None
        assert active_111.purge_type == PurgeType.WAR_END
        assert active_222.purge_type == PurgeType.GLOBAL

    async def test_add_cancellation(self, test_session: AsyncSession) -> None:
        """Test adding cancellation vote."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_cancellation(purge_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.cancelled_by

    async def test_add_cancellation_duplicate(self, test_session: AsyncSession) -> None:
        """Test that cancellation votes are not duplicated."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_cancellation(purge_id=record.id, user_id=789)
        await service.add_cancellation(purge_id=record.id, user_id=789)
        updated = await service.get_purge(record.id)
        assert updated is not None
        assert updated.cancelled_by.count(789) == 1

    async def test_add_cancellation_not_found(self, test_session: AsyncSession) -> None:
        """Test adding cancellation to non-existent purge."""
        service = PurgeService(test_session)
        result = await service.add_cancellation(purge_id=99999, user_id=789)
        assert result is None

    async def test_add_confirmation_not_found(self, test_session: AsyncSession) -> None:
        """Test adding confirmation to non-existent purge."""
        service = PurgeService(test_session)
        result = await service.add_confirmation(purge_id=99999, user_id=789)
        assert result is None

    async def test_remove_confirmation_not_found(self, test_session: AsyncSession) -> None:
        """Test removing confirmation from non-existent purge."""
        service = PurgeService(test_session)
        result = await service.remove_confirmation(purge_id=99999, user_id=789)
        assert result is None

    async def test_remove_confirmation_not_present(self, test_session: AsyncSession) -> None:
        """Test removing confirmation that does not exist."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.remove_confirmation(purge_id=record.id, user_id=999)
        assert updated is not None
        assert 999 not in updated.confirmed_by

    async def test_add_user_result(self, test_session: AsyncSession) -> None:
        """Test adding user result."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        result = await service.add_user_result(
            purge_id=record.id,
            user_id=789,
            action_type="cleaned",
            roles_before=[100, 200],
            roles_after=[300],
        )

        assert result is not None
        assert result.user_id == 789
        assert result.action_type == "cleaned"
        assert result.roles_before == [100, 200]
        assert result.roles_after == [300]

    async def test_add_user_result_with_in_affected(self, test_session: AsyncSession) -> None:
        """Test adding user result with in_affected_group."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        result = await service.add_user_result(
            purge_id=record.id,
            user_id=789,
            action_type="promoted",
            roles_before=[100],
            roles_after=[200],
            in_affected_group=True,
        )

        assert result is not None
        assert result.in_affected_group is True

    async def test_update_status_with_scheduled_for(self, test_session: AsyncSession) -> None:
        """Test updating status with new scheduled_for."""
        service = PurgeService(test_session)

        original_scheduled = datetime.now(UTC) + timedelta(days=3)
        new_scheduled = datetime.now(UTC) + timedelta(minutes=2)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=original_scheduled,
        )

        updated = await service.update_status(
            purge_id=record.id,
            status=PurgeStatus.AUTHORIZED,
            scheduled_for=new_scheduled,
        )

        assert updated is not None
        assert updated.scheduled_for == new_scheduled

    async def test_clear_cancellations(self, test_session: AsyncSession) -> None:
        """Test clearing cancellation votes."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Add some cancellation votes
        await service.add_cancellation(purge_id=record.id, user_id=111)
        await service.add_cancellation(purge_id=record.id, user_id=222)

        # Verify they were added
        updated = await service.get_purge(record.id)
        assert updated is not None
        assert len(updated.cancelled_by) == 2

        # Clear votes
        cleared = await service.clear_cancellations(purge_id=record.id)
        assert cleared is not None
        assert cleared.cancelled_by == []

    async def test_clear_cancellations_empty(self, test_session: AsyncSession) -> None:
        """Test clearing votes when there are none."""
        service = PurgeService(test_session)

        record = await service.create_purge(
            guild_id=123,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Clear without existing votes
        cleared = await service.clear_cancellations(purge_id=record.id)
        assert cleared is not None
        assert cleared.cancelled_by == []

    async def test_clear_cancellations_not_found(self, test_session: AsyncSession) -> None:
        """Test clearing votes from non-existent purge."""
        service = PurgeService(test_session)
        result = await service.clear_cancellations(purge_id=99999)
        assert result is None

    async def test_get_cancel_pending_purges(self, test_session: AsyncSession) -> None:
        """Test getting purges with pending cancellation."""
        service = PurgeService(test_session)

        # Create a PENDING purge
        await service.create_purge(
            guild_id=111,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Create a purge and set it to CANCEL_PENDING
        record2 = await service.create_purge(
            guild_id=222,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record2.id, status=PurgeStatus.CANCEL_PENDING)

        # Create another AUTHORIZED purge
        record3 = await service.create_purge(
            guild_id=333,
            purge_type=PurgeType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purge_id=record3.id, status=PurgeStatus.AUTHORIZED)

        cancel_pending = await service.get_cancel_pending_purges()
        assert len(cancel_pending) == 1
        assert cancel_pending[0].guild_id == 222
        assert cancel_pending[0].status == PurgeStatus.CANCEL_PENDING
