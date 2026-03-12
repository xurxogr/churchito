"""Modelo para solicitudes de verificacion de usuarios."""

from datetime import UTC, datetime
from typing import Any

from nanoid import generate
from sqlalchemy import JSON, BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base
from discord_bot.verification.enums import VerificationStatus, VerificationType


def _generate_public_id() -> str:
    """Genera un ID público único usando NanoID."""
    return str(generate(size=21))


class VerificationRequest(Base):
    """Modelo para solicitudes de verificacion de usuarios.

    Almacena el estado y datos de cada solicitud de verificacion,
    incluyendo capturas de pantalla y resultado de la revision.
    """

    __tablename__ = "verification_requests"
    __table_args__ = (
        Index("ix_verification_guild_id", "guild_id"),
        Index("ix_verification_user_id", "user_id"),
        Index("ix_verification_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(21), unique=True, nullable=False, default=_generate_public_id
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    verification_type: Mapped[str] = mapped_column(
        String(20), default=VerificationType.REGULAR, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default=VerificationStatus.PENDING_SCREENSHOTS, nullable=False
    )

    # URLs de las capturas de pantalla
    screenshot_1_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_2_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Información del jugador extraída por OCR (name, regiment, level, faction, shard, etc.)
    player_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Informacion del moderador que reviso
    reviewed_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_by_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ID del mensaje de moderacion (se edita conforme avanza la verificacion)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    screenshots_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Representacion en cadena.

        Returns:
            str: Representacion en cadena de la solicitud
        """
        return (
            f"<VerificationRequest(id={self.id}, guild_id={self.guild_id}, "
            f"user_id={self.user_id}, status={self.status!r})>"
        )
