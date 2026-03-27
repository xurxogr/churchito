"""Moderator authorization view.

Buttons in this view don't have their own callbacks.
Interactions are handled by the cog's on_interaction listener,
which allows them to work even after bot restart.
"""

import discord

from discord_bot.purge.enums import PurgeStatus


class AuthorizeButton(discord.ui.Button["ModAuthorizationView"]):
    """Button to authorize a purge."""

    def __init__(
        self,
        public_id: str,
        label: str = "Authorize purge",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Initialize the authorize button.

        Args:
            public_id (str): Public ID of the purge record (NanoID).
            label (str): Button text.
            style (discord.ButtonStyle): Button style.
        """
        super().__init__(
            label=label,
            style=style,
            custom_id=f"purge:authorize:{public_id}",
        )


class CancelButton(discord.ui.Button["ModAuthorizationView"]):
    """Button to cancel a purge."""

    def __init__(
        self,
        public_id: str,
        label: str = "Stop purge",
    ) -> None:
        """Initialize the cancel button.

        Args:
            public_id (str): Public ID of the purge record (NanoID).
            label (str): Button text.
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"purge:cancel:{public_id}",
        )


class ModAuthorizationView(discord.ui.View):
    """View with authorize/cancel buttons for moderators.

    This view is attached to authorization messages in the
    moderation channel. Displayed buttons depend on purge status:
    - PENDING: Shows authorize button
    - AUTHORIZED: Shows cancel/stop button
    """

    def __init__(
        self,
        public_id: str,
        status: PurgeStatus,
        authorize_label: str = "Authorize purge",
        cancel_label: str = "Stop purge",
        button_style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Initialize the authorization view.

        Args:
            public_id (str): Public ID of the purge record (NanoID).
            status (PurgeStatus): Current purge status.
            authorize_label (str): Authorize button text.
            cancel_label (str): Cancel button text.
            button_style (discord.ButtonStyle): Authorize button style.
        """
        super().__init__(timeout=None)

        if status == PurgeStatus.PENDING:
            self.add_item(
                AuthorizeButton(public_id=public_id, label=authorize_label, style=button_style)
            )
        elif status in (PurgeStatus.AUTHORIZED, PurgeStatus.CANCEL_PENDING):
            self.add_item(CancelButton(public_id=public_id, label=cancel_label))
