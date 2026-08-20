"""Rejection reason selection view."""

import discord

from discord_bot.verification.views.protocols import get_verification_cog
from discord_bot.verification.views.rejection_modal import RejectionReasonModal


class ReasonSelect(discord.ui.Select["RejectionReasonView"]):
    """Rejection reason selector."""

    def __init__(
        self,
        public_id: str,
        options: list[discord.SelectOption],
        reasons: list[str],
        placeholder: str,
        modal_title: str,
        modal_label: str,
        modal_placeholder: str,
    ) -> None:
        """Initialize the selector.

        Args:
            public_id (str): Public request ID (NanoID).
            options (list[discord.SelectOption]): Selector options.
            reasons (list[str]): Full reasons, indexed by option value.
            placeholder (str): Placeholder text.
            modal_title (str): Custom reason modal title.
            modal_label (str): Modal text field label.
            modal_placeholder (str): Modal text field placeholder.
        """
        super().__init__(
            placeholder=placeholder,
            options=options,
            custom_id=f"verification:reject_reason:{public_id}",
        )
        self.public_id = public_id
        self.reasons = reasons
        self.modal_title = modal_title
        self.modal_label = modal_label
        self.modal_placeholder = modal_placeholder

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Handle rejection reason selection.

        Args:
            interaction (discord.Interaction[discord.Client]): Moderator interaction.
        """
        selected = self.values[0]

        if selected == "__OTHER__":
            modal = RejectionReasonModal(
                public_id=self.public_id,
                title=self.modal_title,
                label=self.modal_label,
                placeholder=self.modal_placeholder,
            )
            await interaction.response.send_modal(modal)
        else:
            # Option values are indexes into the full reasons list: the
            # 100-character option value would otherwise truncate the reason
            index = int(selected) if selected.isdigit() else -1
            cog = get_verification_cog(interaction)
            if cog and 0 <= index < len(self.reasons):
                await cog.handle_reject(
                    interaction=interaction,
                    public_id=self.public_id,
                    reason=self.reasons[index],
                )

        if self.view:
            self.view.stop()


class RejectionReasonView(discord.ui.View):
    """View with dropdown to select rejection reason.

    Shows configurable predefined options plus an "Other" option
    that opens a modal for custom text.
    """

    def __init__(
        self,
        public_id: str,
        reasons: list[str],
        other_label: str = "Other reason...",
        other_description: str = "Write a custom reason",
        placeholder: str = "Select the rejection reason...",
        modal_title: str = "Rejection Reason",
        modal_label: str = "Reason",
        modal_placeholder: str = "Explain why the verification is being rejected...",
    ) -> None:
        """Initialize the selection view.

        Args:
            public_id (str): Public request ID (NanoID).
            reasons (list[str]): List of predefined reasons.
            other_label (str): Label for the "Other" option.
            other_description (str): Description for the "Other" option.
            placeholder (str): Selector placeholder text.
            modal_title (str): Custom reason modal title.
            modal_label (str): Modal text field label.
            modal_placeholder (str): Modal text field placeholder.
        """
        super().__init__(timeout=60)

        # The value is the index into the reasons list: values must be unique
        # (Discord rejects the whole select on duplicates, and two reasons may
        # share their first 100 characters) and the callback recovers the full
        # reason instead of the 100-character truncation
        valid_reasons = [reason for reason in reasons if reason.strip()]
        options = [
            discord.SelectOption(label=reason[:100], value=str(index))
            for index, reason in enumerate(valid_reasons)
        ]
        options.append(
            discord.SelectOption(
                label=other_label,
                value="__OTHER__",
                description=other_description,
            )
        )

        self.add_item(
            ReasonSelect(
                public_id=public_id,
                options=options,
                reasons=valid_reasons,
                placeholder=placeholder,
                modal_title=modal_title,
                modal_label=modal_label,
                modal_placeholder=modal_placeholder,
            )
        )
