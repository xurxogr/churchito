"""Verification panel view."""

import discord

from discord_bot.verification.enums import VerificationType
from discord_bot.verification.views.protocols import get_verification_cog


class VerificationButton(discord.ui.Button["VerificationPanelView"]):
    """Verification button with configurable type."""

    def __init__(
        self,
        label: str,
        verification_type: VerificationType,
        style: discord.ButtonStyle,
        custom_id: str,
    ) -> None:
        """Initialize the verification button.

        Args:
            label (str): Button text
            verification_type (VerificationType): Verification type
            style (discord.ButtonStyle): Button style
            custom_id (str): Unique button ID
        """
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.verification_type = verification_type

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Handle verification button click.

        Args:
            interaction (discord.Interaction[discord.Client]): User interaction
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.handle_verification_start(
            interaction=interaction, verification_type=self.verification_type
        )


class VerificationPanelView(discord.ui.View):
    """Persistent view with verification buttons.

    This view is displayed in the verification channel and allows
    users to start the verification process.
    """

    def __init__(
        self,
        verify_label: str = "Verify",
        ally_label: str = "Verify as Ally",
    ) -> None:
        """Initialize the panel view.

        Args:
            verify_label (str): Normal verification button text
            ally_label (str): Ally verification button text
        """
        super().__init__(timeout=None)

        self.add_item(
            VerificationButton(
                label=verify_label,
                verification_type=VerificationType.REGULAR,
                style=discord.ButtonStyle.primary,
                custom_id=f"verification:{VerificationType.REGULAR}",
            )
        )
        self.add_item(
            VerificationButton(
                label=ally_label,
                verification_type=VerificationType.ALLY,
                style=discord.ButtonStyle.secondary,
                custom_id=f"verification:{VerificationType.ALLY}",
            )
        )
