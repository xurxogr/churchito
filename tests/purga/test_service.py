"""Tests para PurgaService."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.purga.enums import PurgaStatus, PurgaType
from discord_bot.purga.service import PurgaService


class TestPurgaService:
    """Tests para PurgaService."""

    async def test_create_purga(self, test_session: AsyncSession) -> None:
        """Probar creación de purga."""
        service = PurgaService(test_session)
        scheduled_for = datetime.now(UTC) + timedelta(days=3)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={"test": "config"},
            scheduled_for=scheduled_for,
        )

        assert record.id is not None
        assert record.guild_id == 123
        assert record.purga_type == PurgaType.WAR_END
        assert record.status == PurgaStatus.PENDING
        assert record.initiated_by == 456
        assert record.authorized_by == [456]  # Initiator auto-authorizes
        assert record.confirmed_by == []
        assert record.config_snapshot == {"test": "config"}
        assert record.scheduled_for == scheduled_for

    async def test_create_purga_with_expiration(self, test_session: AsyncSession) -> None:
        """Probar creación de purga con expiración."""
        service = PurgaService(test_session)
        scheduled_for = datetime.now(UTC) + timedelta(days=3)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=scheduled_for,
            expires_at=expires_at,
        )

        assert record.expires_at == expires_at

    async def test_get_purga(self, test_session: AsyncSession) -> None:
        """Probar obtención de purga por ID."""
        service = PurgaService(test_session)

        created = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        retrieved = await service.get_purga(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.guild_id == 123

    async def test_get_purga_not_found(self, test_session: AsyncSession) -> None:
        """Probar obtención de purga inexistente."""
        service = PurgaService(test_session)
        result = await service.get_purga(99999)
        assert result is None

    async def test_get_active_purga(self, test_session: AsyncSession) -> None:
        """Probar obtención de purga activa."""
        service = PurgaService(test_session)

        await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        active = await service.get_active_purga(123)
        assert active is not None
        assert active.status == PurgaStatus.PENDING

    async def test_get_active_purga_none(self, test_session: AsyncSession) -> None:
        """Probar obtención de purga activa cuando no hay ninguna."""
        service = PurgaService(test_session)
        active = await service.get_active_purga(123)
        assert active is None

    async def test_get_active_purga_ignores_completed(self, test_session: AsyncSession) -> None:
        """Probar que get_active_purga ignora purgas completadas."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purga_id=record.id, status=PurgaStatus.CANCELLED)

        active = await service.get_active_purga(123)
        assert active is None

    async def test_update_mod_message(self, test_session: AsyncSession) -> None:
        """Probar actualización de IDs de mensaje de moderación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.update_mod_message(purga_id=record.id, channel_id=111, message_id=222)

        updated = await service.get_purga(record.id)
        assert updated is not None
        assert updated.mod_channel_id == 111
        assert updated.mod_message_id == 222

    async def test_update_user_message(self, test_session: AsyncSession) -> None:
        """Probar actualización de IDs de mensaje de usuarios."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.update_user_message(purga_id=record.id, channel_id=333, message_id=444)

        updated = await service.get_purga(record.id)
        assert updated is not None
        assert updated.user_channel_id == 333
        assert updated.user_message_id == 444

    async def test_add_authorization(self, test_session: AsyncSession) -> None:
        """Probar añadir autorización."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_authorization(purga_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.authorized_by
        assert len(updated.authorized_by) == 2  # Initiator + new

    async def test_add_authorization_duplicate(self, test_session: AsyncSession) -> None:
        """Probar que no se duplican autorizaciones."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_authorization(purga_id=record.id, user_id=456)
        updated = await service.get_purga(record.id)
        assert updated is not None
        assert updated.authorized_by.count(456) == 1

    async def test_add_authorization_not_found(self, test_session: AsyncSession) -> None:
        """Probar añadir autorización a purga inexistente."""
        service = PurgaService(test_session)
        result = await service.add_authorization(purga_id=99999, user_id=789)
        assert result is None

    async def test_add_confirmation(self, test_session: AsyncSession) -> None:
        """Probar añadir confirmación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_confirmation(purga_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.confirmed_by

    async def test_add_confirmation_duplicate(self, test_session: AsyncSession) -> None:
        """Probar que no se duplican confirmaciones."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_confirmation(purga_id=record.id, user_id=789)
        await service.add_confirmation(purga_id=record.id, user_id=789)
        updated = await service.get_purga(record.id)
        assert updated is not None
        assert updated.confirmed_by.count(789) == 1

    async def test_remove_confirmation(self, test_session: AsyncSession) -> None:
        """Probar eliminar confirmación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.add_confirmation(purga_id=record.id, user_id=789)

        updated = await service.remove_confirmation(purga_id=record.id, user_id=789)
        assert updated is not None
        assert 789 not in updated.confirmed_by

    async def test_update_status_to_authorized(self, test_session: AsyncSession) -> None:
        """Probar actualización de estado a autorizado."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.update_status(purga_id=record.id, status=PurgaStatus.AUTHORIZED)

        assert updated is not None
        assert updated.status == PurgaStatus.AUTHORIZED
        assert updated.authorized_at is not None

    async def test_update_status_to_executed(self, test_session: AsyncSession) -> None:
        """Probar actualización de estado a ejecutado."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        execution_result = {"purged": 10, "promoted": 5}
        updated = await service.update_status(
            purga_id=record.id,
            status=PurgaStatus.EXECUTED,
            execution_result=execution_result,
        )

        assert updated is not None
        assert updated.status == PurgaStatus.EXECUTED
        assert updated.executed_at is not None
        assert updated.execution_result == execution_result

    async def test_update_status_not_found(self, test_session: AsyncSession) -> None:
        """Probar actualización de estado de purga inexistente."""
        service = PurgaService(test_session)
        result = await service.update_status(purga_id=99999, status=PurgaStatus.CANCELLED)
        assert result is None

    async def test_get_pending_purgas(self, test_session: AsyncSession) -> None:
        """Probar obtención de purgas pendientes."""
        service = PurgaService(test_session)

        await service.create_purga(
            guild_id=111,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        record2 = await service.create_purga(
            guild_id=222,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purga_id=record2.id, status=PurgaStatus.CANCELLED)

        pending = await service.get_pending_purgas()
        assert len(pending) == 1
        assert pending[0].guild_id == 111

    async def test_get_authorized_purgas(self, test_session: AsyncSession) -> None:
        """Probar obtención de purgas autorizadas."""
        service = PurgaService(test_session)

        await service.create_purga(
            guild_id=111,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        record2 = await service.create_purga(
            guild_id=222,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purga_id=record2.id, status=PurgaStatus.AUTHORIZED)

        authorized = await service.get_authorized_purgas()
        assert len(authorized) == 1
        assert authorized[0].guild_id == 222

    async def test_different_guilds_isolated(self, test_session: AsyncSession) -> None:
        """Probar que diferentes guilds tienen datos aislados."""
        service = PurgaService(test_session)

        await service.create_purga(
            guild_id=111,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.create_purga(
            guild_id=222,
            purga_type=PurgaType.GLOBAL,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        active_111 = await service.get_active_purga(111)
        active_222 = await service.get_active_purga(222)

        assert active_111 is not None
        assert active_222 is not None
        assert active_111.purga_type == PurgaType.WAR_END
        assert active_222.purga_type == PurgaType.GLOBAL

    async def test_add_cancellation(self, test_session: AsyncSession) -> None:
        """Probar añadir voto de cancelación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.add_cancellation(purga_id=record.id, user_id=789)
        assert updated is not None
        assert 789 in updated.cancelled_by

    async def test_add_cancellation_duplicate(self, test_session: AsyncSession) -> None:
        """Probar que no se duplican votos de cancelación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        await service.add_cancellation(purga_id=record.id, user_id=789)
        await service.add_cancellation(purga_id=record.id, user_id=789)
        updated = await service.get_purga(record.id)
        assert updated is not None
        assert updated.cancelled_by.count(789) == 1

    async def test_add_cancellation_not_found(self, test_session: AsyncSession) -> None:
        """Probar añadir cancelación a purga inexistente."""
        service = PurgaService(test_session)
        result = await service.add_cancellation(purga_id=99999, user_id=789)
        assert result is None

    async def test_add_confirmation_not_found(self, test_session: AsyncSession) -> None:
        """Probar añadir confirmación a purga inexistente."""
        service = PurgaService(test_session)
        result = await service.add_confirmation(purga_id=99999, user_id=789)
        assert result is None

    async def test_remove_confirmation_not_found(self, test_session: AsyncSession) -> None:
        """Probar eliminar confirmación de purga inexistente."""
        service = PurgaService(test_session)
        result = await service.remove_confirmation(purga_id=99999, user_id=789)
        assert result is None

    async def test_remove_confirmation_not_present(self, test_session: AsyncSession) -> None:
        """Probar eliminar confirmación que no existe."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        updated = await service.remove_confirmation(purga_id=record.id, user_id=999)
        assert updated is not None
        assert 999 not in updated.confirmed_by

    async def test_add_user_result(self, test_session: AsyncSession) -> None:
        """Probar añadir resultado de usuario."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        result = await service.add_user_result(
            purga_id=record.id,
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
        """Probar añadir resultado de usuario con in_affected_group."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        result = await service.add_user_result(
            purga_id=record.id,
            user_id=789,
            action_type="promoted",
            roles_before=[100],
            roles_after=[200],
            in_affected_group=True,
        )

        assert result is not None
        assert result.in_affected_group is True

    async def test_update_status_with_scheduled_for(self, test_session: AsyncSession) -> None:
        """Probar actualización de estado con nuevo scheduled_for."""
        service = PurgaService(test_session)

        original_scheduled = datetime.now(UTC) + timedelta(days=3)
        new_scheduled = datetime.now(UTC) + timedelta(minutes=2)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=original_scheduled,
        )

        updated = await service.update_status(
            purga_id=record.id,
            status=PurgaStatus.AUTHORIZED,
            scheduled_for=new_scheduled,
        )

        assert updated is not None
        assert updated.scheduled_for == new_scheduled

    async def test_clear_cancellations(self, test_session: AsyncSession) -> None:
        """Probar limpiar votos de cancelación."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Añadir algunos votos de cancelación
        await service.add_cancellation(purga_id=record.id, user_id=111)
        await service.add_cancellation(purga_id=record.id, user_id=222)

        # Verificar que se añadieron
        updated = await service.get_purga(record.id)
        assert updated is not None
        assert len(updated.cancelled_by) == 2

        # Limpiar votos
        cleared = await service.clear_cancellations(purga_id=record.id)
        assert cleared is not None
        assert cleared.cancelled_by == []

    async def test_clear_cancellations_empty(self, test_session: AsyncSession) -> None:
        """Probar limpiar votos cuando no hay ninguno."""
        service = PurgaService(test_session)

        record = await service.create_purga(
            guild_id=123,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Limpiar sin votos existentes
        cleared = await service.clear_cancellations(purga_id=record.id)
        assert cleared is not None
        assert cleared.cancelled_by == []

    async def test_clear_cancellations_not_found(self, test_session: AsyncSession) -> None:
        """Probar limpiar votos de purga inexistente."""
        service = PurgaService(test_session)
        result = await service.clear_cancellations(purga_id=99999)
        assert result is None

    async def test_get_cancel_pending_purgas(self, test_session: AsyncSession) -> None:
        """Probar obtención de purgas con cancelación pendiente."""
        service = PurgaService(test_session)

        # Crear una purga PENDING
        await service.create_purga(
            guild_id=111,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )

        # Crear una purga y ponerla en CANCEL_PENDING
        record2 = await service.create_purga(
            guild_id=222,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purga_id=record2.id, status=PurgaStatus.CANCEL_PENDING)

        # Crear otra purga AUTHORIZED
        record3 = await service.create_purga(
            guild_id=333,
            purga_type=PurgaType.WAR_END,
            initiated_by=456,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=3),
        )
        await service.update_status(purga_id=record3.id, status=PurgaStatus.AUTHORIZED)

        cancel_pending = await service.get_cancel_pending_purgas()
        assert len(cancel_pending) == 1
        assert cancel_pending[0].guild_id == 222
        assert cancel_pending[0].status == PurgaStatus.CANCEL_PENDING
