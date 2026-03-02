"""Servicio para operaciones de verificacion de usuarios."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.verification.enums import VerificationStatus, VerificationType
from discord_bot.verification.models import VerificationRequest

logger = logging.getLogger(__name__)


class VerificationService:
    """Servicio para operaciones CRUD de verificacion.

    Maneja la creacion, actualizacion y consulta de solicitudes
    de verificacion de usuarios.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Inicializar el servicio de verificacion.

        Args:
            session (AsyncSession): Sesion de base de datos
        """
        self._session = session

    async def create_request(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        guild_name: str,
        verification_type: VerificationType,
    ) -> VerificationRequest:
        """Crear una nueva solicitud de verificacion.

        Args:
            guild_id (int): ID del guild
            user_id (int): ID del usuario
            username (str): Nombre de usuario de Discord
            guild_name (str): Nombre del guild
            verification_type (VerificationType): Tipo de verificacion

        Returns:
            VerificationRequest: Solicitud creada
        """
        request = VerificationRequest(
            guild_id=guild_id,
            user_id=user_id,
            username=username,
            verification_type=verification_type,
            status=VerificationStatus.PENDING_SCREENSHOTS,
        )
        self._session.add(request)
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Solicitud de verificacion creada: "
            f"{username}, type={verification_type} (ID: {request.id})"
        )
        return request

    async def get_request(self, request_id: int) -> VerificationRequest | None:
        """Obtener una solicitud por ID.

        Args:
            request_id (int): ID de la solicitud

        Returns:
            VerificationRequest | None: Solicitud o None si no existe
        """
        result = await self._session.execute(
            select(VerificationRequest).where(VerificationRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_user(self, guild_id: int, user_id: int) -> VerificationRequest | None:
        """Obtener solicitud pendiente de un usuario.

        Busca solicitudes con estado PENDING_SCREENSHOTS o PENDING_REVIEW.

        Args:
            guild_id (int): ID del guild
            user_id (int): ID del usuario

        Returns:
            VerificationRequest | None: Solicitud pendiente o None
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_any_pending_by_user(self, user_id: int) -> VerificationRequest | None:
        """Obtener cualquier solicitud pendiente de un usuario en cualquier guild.

        Busca solicitudes con estado PENDING_SCREENSHOTS (esperando capturas).
        Util para recuperar verificaciones cuando el bot reinicia.

        Args:
            user_id (int): ID del usuario

        Returns:
            VerificationRequest | None: Solicitud pendiente o None
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.user_id == user_id,
                VerificationRequest.status == VerificationStatus.PENDING_SCREENSHOTS,
            )
            .order_by(VerificationRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_pending_screenshots(self) -> list[VerificationRequest]:
        """Obtener todas las solicitudes esperando capturas.

        Util para restaurar el estado en memoria cuando el bot reinicia.

        Returns:
            list[VerificationRequest]: Lista de solicitudes pendientes
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.status == VerificationStatus.PENDING_SCREENSHOTS,
            )
        )
        return list(result.scalars().all())

    async def get_all_pending(self) -> list[VerificationRequest]:
        """Obtener todas las solicitudes pendientes (screenshots o review).

        Util para limpiar verificaciones de usuarios que salieron del servidor.

        Returns:
            list[VerificationRequest]: Lista de solicitudes pendientes
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
            )
        )
        return list(result.scalars().all())

    async def get_user_history(self, guild_id: int, user_id: int) -> list[VerificationRequest]:
        """Obtener historial de verificaciones de un usuario.

        Args:
            guild_id (int): ID del guild
            user_id (int): ID del usuario

        Returns:
            list[VerificationRequest]: Lista de todas las solicitudes
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
            )
            .order_by(VerificationRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_screenshots(
        self, request_id: int, url1: str, url2: str, guild_name: str
    ) -> VerificationRequest | None:
        """Actualizar solicitud con las capturas de pantalla.

        Cambia el estado a PENDING_REVIEW.

        Args:
            request_id (int): ID de la solicitud
            url1 (str): URL de la primera captura
            url2 (str): URL de la segunda captura
            guild_name (str): Nombre del guild

        Returns:
            VerificationRequest | None: Solicitud actualizada o None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.screenshot_1_url = url1
        request.screenshot_2_url = url2
        request.status = VerificationStatus.PENDING_REVIEW
        request.screenshots_submitted_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(f"[{guild_name}] Capturas actualizadas: {request.username} (ID: {request_id})")
        return request

    async def set_mod_message_id(
        self,
        request_id: int,
        message_id: int,
    ) -> None:
        """Guardar ID del mensaje de moderacion.

        Args:
            request_id (int): ID de la solicitud
            message_id (int): ID del mensaje en el canal de moderacion
        """
        request = await self.get_request(request_id)
        if not request:
            return

        request.mod_message_id = message_id
        await self._session.flush()

    async def approve(
        self, request_id: int, reviewer_id: int, reviewer_username: str
    ) -> VerificationRequest | None:
        """Aprobar una solicitud de verificacion.

        Args:
            request_id (int): ID de la solicitud
            reviewer_id (int): ID del moderador
            reviewer_username (str): Nombre del moderador

        Returns:
            VerificationRequest | None: Solicitud actualizada o None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.APPROVED
        request.reviewed_by_id = reviewer_id
        request.reviewed_by_username = reviewer_username
        request.reviewed_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(f"Solicitud {request_id} aprobada por {reviewer_username} ({reviewer_id})")
        return request

    async def reject(
        self, request_id: int, reviewer_id: int, reviewer_username: str, reason: str
    ) -> VerificationRequest | None:
        """Rechazar una solicitud de verificacion.

        Args:
            request_id (int): ID de la solicitud
            reviewer_id (int): ID del moderador
            reviewer_username (str): Nombre del moderador
            reason (str): Motivo del rechazo

        Returns:
            VerificationRequest | None: Solicitud actualizada o None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.REJECTED
        request.reviewed_by_id = reviewer_id
        request.reviewed_by_username = reviewer_username
        request.rejection_reason = reason
        request.reviewed_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(f"Solicitud {request_id} rechazada por {reviewer_username} ({reviewer_id})")
        return request

    async def cancel(self, request_id: int) -> VerificationRequest | None:
        """Cancelar una solicitud de verificacion.

        Usado cuando el usuario sale del servidor.

        Args:
            request_id (int): ID de la solicitud

        Returns:
            VerificationRequest | None: Solicitud actualizada o None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.CANCELLED
        await self._session.flush()

        logger.info(f"Solicitud {request_id} cancelada")
        return request

    async def revert_to_pending_review(self, request_id: int) -> VerificationRequest | None:
        """Revertir una solicitud rechazada a pendiente de revisión.

        Usado para permitir revisión manual de auto-rechazos.

        Args:
            request_id (int): ID de la solicitud

        Returns:
            VerificationRequest | None: Solicitud actualizada o None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        if request.status != VerificationStatus.REJECTED:
            return None

        request.status = VerificationStatus.PENDING_REVIEW
        request.reviewed_by_id = None
        request.reviewed_by_username = None
        request.rejection_reason = None
        request.reviewed_at = None
        await self._session.flush()

        logger.info(f"Solicitud {request_id} revertida a revisión pendiente")
        return request

    async def get_latest_by_user(self, guild_id: int, user_id: int) -> VerificationRequest | None:
        """Obtener la última solicitud de un usuario.

        Args:
            guild_id (int): ID del guild
            user_id (int): ID del usuario

        Returns:
            VerificationRequest | None: Última solicitud o None
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
            )
            .order_by(VerificationRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
