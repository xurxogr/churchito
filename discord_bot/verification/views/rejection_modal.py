"""Rejection reason modal."""

import discord

from discord_bot.verification.views.protocols import get_verification_cog


class RejectionReasonModal(discord.ui.Modal):
    """Modal for entering rejection reason."""

    def __init__(
        self,
        public_id: str,
        title: str = "Rejection Reason",
        label: str = "Reason",
        placeholder: str = "Explain why the verification is being rejected...",
    ) -> None:
        """Initialize the modal.

        Args:
            public_id (str): Public request ID (NanoID)
            title (str): Modal title
            label (str): Text field label
            placeholder (str): Field help text
        """
        super().__init__(title=title)
        self.public_id = public_id

        self.reason: discord.ui.TextInput[RejectionReasonModal] = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Process modal submission.

        Args:
            interaction (discord.Interaction): Moderator interaction
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.handle_reject(
            interaction=interaction,
            public_id=self.public_id,
            reason=self.reason.value,
        )
