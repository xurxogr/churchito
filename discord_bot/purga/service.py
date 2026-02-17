"""Servicio para operaciones de purga en base de datos."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.purga.enums import PurgaStatus, PurgaType
from discord_bot.purga.models import PurgaRecord, PurgaUserResult


class PurgaService:
    """Servicio para operaciones de purga en base de datos."""

    def __init__(self, session: AsyncSession) -> None:
        """Inicializar el servicio.

        Args:
            session (AsyncSession): Sesión de base de datos.
        """
        self._session = session

    async def create_purga(
        self,
        guild_id: int,
        purga_type: PurgaType,
        initiated_by: int,
        config_snapshot: dict[str, Any],
        scheduled_for: datetime,
        expires_at: datetime | None = None,
    ) -> PurgaRecord:
        """Crear un nuevo registro de purga.

        Args:
            guild_id (int): ID del guild.
            purga_type (PurgaType): Tipo de purga.
            initiated_by (int): ID del usuario que inició.
            config_snapshot (dict[str, Any]): Snapshot de la configuración.
            scheduled_for (datetime): Fecha programada para ejecución.
            expires_at (datetime | None): Fecha de expiración para autorizaciones.

        Returns:
            PurgaRecord: Registro creado.
        """
        record = PurgaRecord(
            guild_id=guild_id,
            purga_type=purga_type,
            status=PurgaStatus.PENDING,
            initiated_by=initiated_by,
            authorized_by=[initiated_by],  # El iniciador cuenta como primera autorización
            cancelled_by=[],
            confirmed_by=[],
            config_snapshot=config_snapshot,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_purga(self, purga_id: int) -> PurgaRecord | None:
        """Obtener una purga por ID.

        Args:
            purga_id (int): ID de la purga.

        Returns:
            PurgaRecord | None: Registro si existe.
        """
        result = await self._session.execute(select(PurgaRecord).where(PurgaRecord.id == purga_id))
        return result.scalar_one_or_none()

    async def get_active_purga(self, guild_id: int) -> PurgaRecord | None:
        """Obtener la purga activa de un guild.

        Una purga está activa si su estado es PENDING o AUTHORIZED.

        Args:
            guild_id (int): ID del guild.

        Returns:
            PurgaRecord | None: Purga activa si existe.
        """
        result = await self._session.execute(
            select(PurgaRecord).where(
                PurgaRecord.guild_id == guild_id,
                PurgaRecord.status.in_([PurgaStatus.PENDING, PurgaStatus.AUTHORIZED]),
            )
        )
        return result.scalar_one_or_none()

    async def get_purga_by_mod_message(self, guild_id: int, message_id: int) -> PurgaRecord | None:
        """Obtener una purga por el ID del mensaje de moderación.

        Args:
            guild_id (int): ID del guild.
            message_id (int): ID del mensaje de moderación.

        Returns:
            PurgaRecord | None: Registro si existe.
        """
        result = await self._session.execute(
            select(PurgaRecord).where(
                PurgaRecord.guild_id == guild_id,
                PurgaRecord.mod_message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_purga_by_user_message(self, guild_id: int, message_id: int) -> PurgaRecord | None:
        """Obtener una purga por el ID del mensaje de usuarios.

        Args:
            guild_id (int): ID del guild.
            message_id (int): ID del mensaje de usuarios.

        Returns:
            PurgaRecord | None: Registro si existe.
        """
        result = await self._session.execute(
            select(PurgaRecord).where(
                PurgaRecord.guild_id == guild_id,
                PurgaRecord.user_message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_mod_message(self, purga_id: int, channel_id: int, message_id: int) -> None:
        """Actualizar IDs del mensaje de moderación.

        Args:
            purga_id (int): ID de la purga.
            channel_id (int): ID del canal.
            message_id (int): ID del mensaje.
        """
        await self._session.execute(
            update(PurgaRecord)
            .where(PurgaRecord.id == purga_id)
            .values(mod_channel_id=channel_id, mod_message_id=message_id)
        )
        await self._session.flush()

    async def update_user_message(self, purga_id: int, channel_id: int, message_id: int) -> None:
        """Actualizar IDs del mensaje de usuarios.

        Args:
            purga_id (int): ID de la purga.
            channel_id (int): ID del canal.
            message_id (int): ID del mensaje.
        """
        await self._session.execute(
            update(PurgaRecord)
            .where(PurgaRecord.id == purga_id)
            .values(user_channel_id=channel_id, user_message_id=message_id)
        )
        await self._session.flush()

    async def add_authorization(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Añadir una autorización a la purga.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que autoriza.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id not in record.authorized_by:
            authorized_by = list(record.authorized_by)
            authorized_by.append(user_id)
            record.authorized_by = authorized_by
            await self._session.flush()

        return record

    async def remove_authorization(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Eliminar una autorización de la purga.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que retira autorización.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id in record.authorized_by:
            authorized_by = list(record.authorized_by)
            authorized_by.remove(user_id)
            record.authorized_by = authorized_by
            await self._session.flush()

        return record

    async def add_cancellation(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Añadir un voto de cancelación a la purga.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que vota por cancelar.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id not in record.cancelled_by:
            cancelled_by = list(record.cancelled_by)
            cancelled_by.append(user_id)
            record.cancelled_by = cancelled_by
            await self._session.flush()

        return record

    async def remove_cancellation(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Eliminar un voto de cancelación de la purga.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que retira su voto.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id in record.cancelled_by:
            cancelled_by = list(record.cancelled_by)
            cancelled_by.remove(user_id)
            record.cancelled_by = cancelled_by
            await self._session.flush()

        return record

    async def add_confirmation(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Añadir una confirmación de usuario.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que confirma.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id not in record.confirmed_by:
            confirmed_by = list(record.confirmed_by)
            confirmed_by.append(user_id)
            record.confirmed_by = confirmed_by
            await self._session.flush()

        return record

    async def remove_confirmation(self, purga_id: int, user_id: int) -> PurgaRecord | None:
        """Eliminar una confirmación de usuario.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario que retira confirmación.

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        if user_id in record.confirmed_by:
            confirmed_by = list(record.confirmed_by)
            confirmed_by.remove(user_id)
            record.confirmed_by = confirmed_by
            await self._session.flush()

        return record

    async def update_status(
        self,
        purga_id: int,
        status: PurgaStatus,
        execution_result: dict[str, Any] | None = None,
        scheduled_for: datetime | None = None,
    ) -> PurgaRecord | None:
        """Actualizar el estado de una purga.

        Args:
            purga_id (int): ID de la purga.
            status (PurgaStatus): Nuevo estado.
            execution_result (dict[str, Any] | None): Resultado de ejecución (opcional).
            scheduled_for (datetime | None): Nueva fecha de ejecución (opcional).

        Returns:
            PurgaRecord | None: Registro actualizado.
        """
        record = await self.get_purga(purga_id)
        if not record:
            return None

        record.status = status

        if scheduled_for is not None:
            record.scheduled_for = scheduled_for

        if status == PurgaStatus.AUTHORIZED:
            record.authorized_at = datetime.now(UTC)
        elif status in (PurgaStatus.EXECUTED, PurgaStatus.FAILED):
            record.executed_at = datetime.now(UTC)
            if execution_result:
                record.execution_result = execution_result

        await self._session.flush()
        return record

    async def get_pending_purgas(self) -> list[PurgaRecord]:
        """Obtener todas las purgas pendientes de autorización.

        Returns:
            list[PurgaRecord]: Lista de purgas pendientes.
        """
        result = await self._session.execute(
            select(PurgaRecord).where(PurgaRecord.status == PurgaStatus.PENDING)
        )
        return list(result.scalars().all())

    async def get_authorized_purgas(self) -> list[PurgaRecord]:
        """Obtener todas las purgas autorizadas pendientes de ejecución.

        Returns:
            list[PurgaRecord]: Lista de purgas autorizadas.
        """
        result = await self._session.execute(
            select(PurgaRecord).where(PurgaRecord.status == PurgaStatus.AUTHORIZED)
        )
        return list(result.scalars().all())

    async def get_ready_to_execute_purgas(self) -> list[PurgaRecord]:
        """Obtener purgas autorizadas listas para ejecutar.

        Returns:
            list[PurgaRecord]: Lista de purgas cuyo scheduled_for ha pasado.
        """
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(PurgaRecord).where(
                PurgaRecord.status == PurgaStatus.AUTHORIZED,
                PurgaRecord.scheduled_for.isnot(None),
                PurgaRecord.scheduled_for <= now,
            )
        )
        return list(result.scalars().all())

    async def get_expired_pending_purgas(self) -> list[PurgaRecord]:
        """Obtener purgas pendientes que han expirado.

        Returns:
            list[PurgaRecord]: Lista de purgas pendientes cuyo expires_at ha pasado.
        """
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(PurgaRecord).where(
                PurgaRecord.status == PurgaStatus.PENDING,
                PurgaRecord.expires_at.isnot(None),
                PurgaRecord.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_guild_purga_history(self, guild_id: int, limit: int = 10) -> list[PurgaRecord]:
        """Obtener historial de purgas de un guild.

        Args:
            guild_id (int): ID del guild.
            limit (int): Número máximo de registros.

        Returns:
            list[PurgaRecord]: Lista de purgas ordenadas por fecha.
        """
        result = await self._session.execute(
            select(PurgaRecord)
            .where(PurgaRecord.guild_id == guild_id)
            .order_by(PurgaRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_user_result(
        self,
        purga_id: int,
        user_id: int,
        action_type: str,
        roles_before: list[int],
        roles_after: list[int],
        in_affected_group: bool | None = None,
    ) -> PurgaUserResult:
        """Añadir un resultado de usuario a la purga.

        Args:
            purga_id (int): ID de la purga.
            user_id (int): ID del usuario.
            action_type (str): Tipo de acción ("cleaned" o "promoted").
            roles_before (list[int]): Roles antes de la purga.
            roles_after (list[int]): Roles después de la purga.
            in_affected_group (bool | None): Si tenía un rol afectado (para promoted).

        Returns:
            PurgaUserResult: Registro creado.
        """
        result = PurgaUserResult(
            purga_id=purga_id,
            user_id=user_id,
            action_type=action_type,
            roles_before=roles_before,
            roles_after=roles_after,
            in_affected_group=in_affected_group,
        )
        self._session.add(result)
        await self._session.flush()
        return result
