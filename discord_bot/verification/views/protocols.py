"""Protocols for verification view typing."""

from typing import Protocol, cast

import discord
from discord.ext import commands

from discord_bot.verification.enums import VerificationType


class VerificationCogProtocol(Protocol):
    """Protocol that defines cog methods used by views."""

    async def handle_verification_start(
        self, interaction: discord.Interaction, verification_type: VerificationType
    ) -> None:
        """Handle verification start."""

    async def handle_accept(self, interaction: discord.Interaction, public_id: str) -> None:
        """Handle verification approval."""

    async def handle_reject(
        self, interaction: discord.Interaction, public_id: str, reason: str
    ) -> None:
        """Handle verification rejection."""

    async def show_rejection_select(self, interaction: discord.Interaction, public_id: str) -> None:
        """Show rejection reason selector."""


def get_verification_cog(
    interaction: discord.Interaction[discord.Client],
) -> VerificationCogProtocol | None:
    """Get the verification cog with the correct type.

    Args:
        interaction (discord.Interaction): Discord interaction

    Returns:
        VerificationCogProtocol | None: Verification cog or None
    """
    bot = cast(commands.Bot, interaction.client)
    cog = bot.get_cog("VerificationCog")
    if not cog:
        return None
    return cast(VerificationCogProtocol, cog)
