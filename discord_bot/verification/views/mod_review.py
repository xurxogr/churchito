"""Review view for moderators.

The buttons in this view do not have their own callbacks.
Interactions are handled by the cog's on_interaction listener,
which allows them to work even after the bot restarts.
"""

import discord


class AcceptButton(discord.ui.Button["ModReviewView"]):
    """Button to accept a verification request."""

    def __init__(self, public_id: str, label: str = "Accept") -> None:
        """Initialize the accept button.

        Args:
            public_id (str): Public request ID (NanoID)
            label (str): Button text
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"verification:accept:{public_id}",
        )


class RejectButton(discord.ui.Button["ModReviewView"]):
    """Button to reject a verification request."""

    def __init__(self, public_id: str, label: str = "Reject") -> None:
        """Initialize the reject button.

        Args:
            public_id (str): Public request ID (NanoID)
            label (str): Button text
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"verification:reject:{public_id}",
        )


class ModReviewView(discord.ui.View):
    """View with accept/reject buttons for moderators.

    This view is attached to review messages in the
    moderation channel.
    """

    def __init__(
        self,
        public_id: str,
        accept_label: str = "Accept",
        reject_label: str = "Reject",
    ) -> None:
        """Initialize the review view.

        Args:
            public_id (str): Public request ID (NanoID)
            accept_label (str): Accept button text
            reject_label (str): Reject button text
        """
        super().__init__(timeout=None)
        self.public_id = public_id

        self.add_item(AcceptButton(public_id=public_id, label=accept_label))
        self.add_item(RejectButton(public_id=public_id, label=reject_label))
