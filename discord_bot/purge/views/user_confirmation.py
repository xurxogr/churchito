"""User confirmation view.

Buttons in this view don't have their own callbacks.
Interactions are handled by the cog's on_interaction listener,
which allows them to work even after bot restart.
"""

import discord


class ConfirmButton(discord.ui.Button["UserConfirmationView"]):
    """Button to confirm staying."""

    def __init__(
        self,
        public_id: str,
        label: str = "Confirm staying",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Initialize the confirm button.

        Args:
            public_id (str): Public ID of the purge record (NanoID).
            label (str): Button text.
            style (discord.ButtonStyle): Button style.
        """
        super().__init__(
            label=label,
            style=style,
            custom_id=f"purge:confirm:{public_id}",
        )


class UserConfirmationView(discord.ui.View):
    """View with confirmation button for users.

    This view is attached to purge messages in the
    user channel.
    """

    def __init__(
        self,
        public_id: str,
        confirm_label: str = "Confirm staying",
        button_style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Initialize the confirmation view.

        Args:
            public_id (str): Public ID of the purge record (NanoID).
            confirm_label (str): Confirm button text.
            button_style (discord.ButtonStyle): Button style.
        """
        super().__init__(timeout=None)

        self.add_item(ConfirmButton(public_id=public_id, label=confirm_label, style=button_style))
