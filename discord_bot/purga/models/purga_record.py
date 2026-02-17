"""Modelo de registro de purga."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from discord_bot.common.models import Base
from discord_bot.purga.enums import PurgaStatus


class PurgaRecord(Base):
    """Registro de una purga.

    Almacena el historial de purgas realizadas, incluyendo estado,
    autorizadores, IDs de mensajes y resultados.
    """

    __tablename__ = "purga_records"
    __table_args__ = (
        Index("ix_purga_guild_id", "guild_id"),
        Index("ix_purga_status", "status"),
        Index("ix_purga_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purga_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=PurgaStatus.PENDING)

    # Usuario que inició la purga
    initiated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # IDs de mensajes para poder eliminarlos si se cancela
    mod_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Lista de IDs de usuarios que autorizaron
    authorized_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Lista de IDs de usuarios que votaron por cancelar
    cancelled_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Lista de IDs de usuarios que confirmaron (reaccionaron en canal de usuarios)
    confirmed_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Configuración usada en esta purga (snapshot)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Resultados de la ejecución (resumen)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Resultados por usuario
    user_results = relationship(
        "PurgaUserResult",
        back_populates="purga",
        cascade="all, delete-orphan",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Representación en cadena.

        Returns:
            str: Representación del registro.
        """
        return (
            f"<PurgaRecord(id={self.id}, guild_id={self.guild_id}, "
            f"type={self.purga_type}, status={self.status})>"
        )
