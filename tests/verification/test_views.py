"""Tests for verification views."""

from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

from discord_bot.verification.views.mod_review import (
    AcceptButton,
    ModReviewView,
    RejectButton,
)
from discord_bot.verification.views.rejection_modal import RejectionReasonModal
from discord_bot.verification.views.rejection_select import (
    ReasonSelect,
    RejectionReasonView,
)
from discord_bot.verification.views.verification_panel import (
    VerificationButton,
    VerificationPanelView,
)


class TestVerificationPanelView:
    """Tests for VerificationPanelView."""

    async def test_init_default_labels(self) -> None:
        """Test initialization with default labels."""
        view = VerificationPanelView()

        assert len(view.children) == 2
        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].label == "Verify"
        assert buttons[1].label == "Verify as Ally"

    async def test_init_custom_labels(self) -> None:
        """Test initialization with custom labels."""
        view = VerificationPanelView(verify_label="Custom Verify", ally_label="Custom Ally")

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].label == "Custom Verify"
        assert buttons[1].label == "Custom Ally"

    async def test_button_custom_ids(self) -> None:
        """Test that buttons have correct custom_id."""
        view = VerificationPanelView()

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].custom_id == "verification:regular"
        assert buttons[1].custom_id == "verification:ally"

    async def test_button_styles(self) -> None:
        """Test button styles."""
        view = VerificationPanelView()

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].style == discord.ButtonStyle.primary
        assert buttons[1].style == discord.ButtonStyle.secondary

    async def test_regular_button_callback(self) -> None:
        """Test regular button callback."""
        view = VerificationPanelView()

        # Mock interaction and bot
        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_verification_start = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        # Get the button and call its callback
        regular_button = view.children[0]
        await regular_button.callback(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")
        mock_cog.handle_verification_start.assert_called_once_with(
            interaction=interaction, verification_type="regular"
        )

    async def test_ally_button_callback(self) -> None:
        """Test ally button callback."""
        view = VerificationPanelView()

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_verification_start = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        ally_button = view.children[1]
        await ally_button.callback(interaction)

        mock_cog.handle_verification_start.assert_called_once_with(
            interaction=interaction, verification_type="ally"
        )

    async def test_button_callback_no_cog(self) -> None:
        """Test callback when cog does not exist."""
        view = VerificationPanelView()

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        # Should not fail
        regular_button = view.children[0]
        await regular_button.callback(interaction)


class TestModReviewView:
    """Tests for ModReviewView."""

    async def test_init_default_labels(self) -> None:
        """Test initialization with default labels."""
        view = ModReviewView(public_id="test123")

        assert len(view.children) == 2
        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.label == "Accept"
        assert reject_btn.label == "Reject"

    async def test_init_custom_labels(self) -> None:
        """Test initialization with custom labels."""
        view = ModReviewView(public_id="test123", accept_label="Approve", reject_label="Deny")

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.label == "Approve"
        assert reject_btn.label == "Deny"

    async def test_button_custom_ids(self) -> None:
        """Test that buttons have custom_id with public_id."""
        view = ModReviewView(public_id="test456")

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.custom_id == "verification:accept:test456"
        assert reject_btn.custom_id == "verification:reject:test456"

    async def test_button_styles(self) -> None:
        """Test button styles."""
        view = ModReviewView(public_id="test123")

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.style == discord.ButtonStyle.success
        assert reject_btn.style == discord.ButtonStyle.danger

    # Buttons do not have their own callbacks.
    # Interactions are handled by the cog's on_interaction.


class TestRejectionReasonView:
    """Tests for RejectionReasonView."""

    async def test_init_creates_select(self) -> None:
        """Test that the select is created."""
        reasons = ["Reason 1", "Reason 2"]
        view = RejectionReasonView(public_id="test123", reasons=reasons)

        assert len(view.children) == 1
        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert isinstance(select, discord.ui.Select)

    async def test_select_options(self) -> None:
        """Test select options."""
        reasons = ["Reason 1", "Reason 2"]
        view = RejectionReasonView(public_id="test123", reasons=reasons)

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # 2 reasons + "Other reason..."
        assert len(select.options) == 3
        assert select.options[0].label == "Reason 1"
        assert select.options[1].label == "Reason 2"
        assert select.options[2].value == "__OTHER__"

    async def test_select_custom_id(self) -> None:
        """Test select custom_id."""
        view = RejectionReasonView(public_id="test456", reasons=["Reason"])

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert select.custom_id == "verification:reject_reason:test456"

    async def test_ignores_empty_reasons(self) -> None:
        """Test that ignores empty reasons."""
        reasons = ["Reason 1", "", "  ", "Reason 2"]
        view = RejectionReasonView(public_id="test123", reasons=reasons)

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # Only 2 valid reasons + "Other"
        assert len(select.options) == 3

    async def test_truncates_long_reasons(self) -> None:
        """Test that truncates long reasons to 100 characters."""
        long_reason = "A" * 150
        view = RejectionReasonView(public_id="test123", reasons=[long_reason])

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert len(select.options[0].label) == 100

    async def test_select_predefined_reason_callback(self) -> None:
        """Test callback with predefined reason."""
        view = RejectionReasonView(public_id="test789", reasons=["Test reason"])

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_reject = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # Set the internal values list directly
        object.__setattr__(select, "_values", ["Test reason"])

        await select.callback(interaction)

        mock_cog.handle_reject.assert_called_once_with(
            interaction=interaction, public_id="test789", reason="Test reason"
        )

    async def test_select_other_reason_callback(self) -> None:
        """Test callback with 'Other reason'."""
        view = RejectionReasonView(public_id="test789", reasons=["Reason"])

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.send_modal = AsyncMock()

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # Set the internal values list directly
        object.__setattr__(select, "_values", ["__OTHER__"])

        await select.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, RejectionReasonModal)

    async def test_select_predefined_reason_callback_no_cog(self) -> None:
        """Test callback with predefined reason when cog does not exist."""
        view = RejectionReasonView(public_id="test789", reasons=["Test reason"])

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        object.__setattr__(select, "_values", ["Test reason"])

        # Should not fail, just return early
        await select.callback(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")


class TestRejectionReasonModal:
    """Tests for RejectionReasonModal."""

    async def test_init(self) -> None:
        """Test modal initialization."""
        modal = RejectionReasonModal(public_id="test123")

        assert modal.public_id == "test123"
        assert modal.title == "Rejection Reason"

    async def test_has_text_input(self) -> None:
        """Test that has a text input field."""
        modal = RejectionReasonModal(public_id="test123")

        # The modal has children (TextInput)
        assert len(modal.children) == 1

    async def test_on_submit_calls_handle_reject(self) -> None:
        """Test that on_submit calls handle_reject."""
        modal = RejectionReasonModal(public_id="test789")

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_reject = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        # Simulate TextInput value using mock
        modal.reason = MagicMock()
        modal.reason.value = "Custom reason"

        await modal.on_submit(interaction)

        mock_cog.handle_reject.assert_called_once_with(
            interaction=interaction, public_id="test789", reason="Custom reason"
        )

    async def test_on_submit_no_cog(self) -> None:
        """Test on_submit when cog does not exist."""
        modal = RejectionReasonModal(public_id="test789")

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        modal.reason = MagicMock()
        modal.reason.value = "Custom reason"

        # Should not fail, just return early
        await modal.on_submit(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")


class TestAutoRejectReviewView:
    """Tests for AutoRejectReviewView."""

    async def test_init_default_label(self) -> None:
        """Test initialization with default label."""
        from discord_bot.verification.views.auto_reject_review import (
            AutoRejectReviewView,
            ReviewButton,
        )

        view = AutoRejectReviewView(public_id="test123")

        assert len(view.children) == 1
        button = next(c for c in view.children if isinstance(c, ReviewButton))
        assert button.label == "Revisar"

    async def test_init_custom_label(self) -> None:
        """Test initialization with custom label."""
        from discord_bot.verification.views.auto_reject_review import (
            AutoRejectReviewView,
            ReviewButton,
        )

        view = AutoRejectReviewView(public_id="test123", review_label="Review Now")

        button = next(c for c in view.children if isinstance(c, ReviewButton))
        assert button.label == "Review Now"

    async def test_button_custom_id(self) -> None:
        """Test that button has correct custom_id."""
        from discord_bot.verification.views.auto_reject_review import (
            AutoRejectReviewView,
            ReviewButton,
        )

        view = AutoRejectReviewView(public_id="test456")

        button = next(c for c in view.children if isinstance(c, ReviewButton))
        assert button.custom_id == "verification:review:test456"

    async def test_timeout_default(self) -> None:
        """Test default timeout (30 minutes)."""
        from discord_bot.verification.views.auto_reject_review import AutoRejectReviewView

        view = AutoRejectReviewView(public_id="test123")
        assert view.timeout == 30 * 60  # 30 minutes in seconds

    async def test_timeout_custom(self) -> None:
        """Test custom timeout."""
        from discord_bot.verification.views.auto_reject_review import AutoRejectReviewView

        view = AutoRejectReviewView(public_id="test123", timeout_minutes=60)
        assert view.timeout == 60 * 60  # 60 minutes in seconds

    async def test_timeout_disabled(self) -> None:
        """Test disabled timeout (0 minutes)."""
        from discord_bot.verification.views.auto_reject_review import AutoRejectReviewView

        view = AutoRejectReviewView(public_id="test123", timeout_minutes=0)
        assert view.timeout is None

    async def test_button_style(self) -> None:
        """Test button style."""
        from discord_bot.verification.views.auto_reject_review import (
            AutoRejectReviewView,
            ReviewButton,
        )

        view = AutoRejectReviewView(public_id="test123")

        button = next(c for c in view.children if isinstance(c, ReviewButton))
        assert button.style == discord.ButtonStyle.secondary
