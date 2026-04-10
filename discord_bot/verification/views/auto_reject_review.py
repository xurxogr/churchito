"""Review view for auto-rejections.

Allows moderators to review verifications that were
auto-rejected within the configured time window.
"""

import discord


class ReviewButton(discord.ui.Button["AutoRejectReviewView"]):
    """Button to review an auto-rejection."""

    def __init__(self, public_id: str, label: str = "Revisar") -> None:
        """Initialize the review button.

        Args:
            public_id (str): Public request ID (NanoID).
            label (str): Button text.
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"verification:review:{public_id}",
        )


class AutoRejectReviewView(discord.ui.View):
    """View with review button for auto-rejections.

    This view is attached to auto-rejection messages during
    the configured time window.
    """

    def __init__(
        self,
        public_id: str,
        review_label: str = "Revisar",
        timeout_minutes: int = 30,
    ) -> None:
        """Initialize the review view.

        Args:
            public_id (str): Public request ID (NanoID).
            review_label (str): Review button text.
            timeout_minutes (int): Minutes until the button expires.
        """
        # Convert minutes to seconds for timeout
        timeout_seconds = timeout_minutes * 60 if timeout_minutes > 0 else None
        super().__init__(timeout=timeout_seconds)
        self.public_id = public_id

        self.add_item(ReviewButton(public_id=public_id, label=review_label))
