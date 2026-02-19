"""Protocolos para tipado de vistas de verificacion."""

from typing import Protocol, cast

import discord
from discord.ext import commands

from discord_bot.verification.enums import VerificationType


class VerificationCogProtocol(Protocol):
    """Protocolo que define los metodos del cog usados por las vistas."""

    async def handle_verification_start(
        self, interaction: discord.Interaction, verification_type: VerificationType
    ) -> None:
        """Manejar inicio de verificacion."""

    async def handle_accept(self, interaction: discord.Interaction, request_id: int) -> None:
        """Manejar aprobacion de verificacion."""

    async def handle_reject(
        self, interaction: discord.Interaction, request_id: int, reason: str
    ) -> None:
        """Manejar rechazo de verificacion."""

    async def show_rejection_select(
        self, interaction: discord.Interaction, request_id: int
    ) -> None:
        """Mostrar selector de motivos de rechazo."""


def get_verification_cog(
    interaction: discord.Interaction[discord.Client],
) -> VerificationCogProtocol | None:
    """Obtener el cog de verificacion con el tipo correcto.

    Args:
        interaction (discord.Interaction): Interaccion de Discord

    Returns:
        VerificationCogProtocol | None: Cog de verificacion o None
    """
    bot = cast(commands.Bot, interaction.client)
    cog = bot.get_cog("VerificationCog")
    if not cog:
        return None
    return cast(VerificationCogProtocol, cog)
