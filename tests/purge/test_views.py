"""Tests for purge views."""

import discord

from discord_bot.purge.enums import PurgeStatus
from discord_bot.purge.views import ModAuthorizationView, UserConfirmationView
from discord_bot.purge.views.mod_authorization import AuthorizeButton, CancelButton
from discord_bot.purge.views.user_confirmation import ConfirmButton


class TestModAuthorizationView:
    """Tests for ModAuthorizationView."""

    async def test_view_creation_pending(self) -> None:
        """Test view creation with PENDING status."""
        view = ModAuthorizationView(public_id="test123", status=PurgeStatus.PENDING)

        assert view.timeout is None
        assert len(view.children) == 1
        assert isinstance(view.children[0], AuthorizeButton)

    async def test_view_creation_authorized(self) -> None:
        """Test view creation with AUTHORIZED status."""
        view = ModAuthorizationView(public_id="test123", status=PurgeStatus.AUTHORIZED)

        assert view.timeout is None
        assert len(view.children) == 1
        assert isinstance(view.children[0], CancelButton)

    async def test_view_custom_authorize_label(self) -> None:
        """Test view with custom authorize label."""
        view = ModAuthorizationView(
            public_id="test123",
            status=PurgeStatus.PENDING,
            authorize_label="Custom Authorize",
        )

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.label == "Custom Authorize"

    async def test_view_custom_cancel_label(self) -> None:
        """Test view with custom cancel label."""
        view = ModAuthorizationView(
            public_id="test123",
            status=PurgeStatus.AUTHORIZED,
            cancel_label="Custom Cancel",
        )

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.label == "Custom Cancel"

    async def test_view_custom_button_style(self) -> None:
        """Test view with custom button style."""
        view = ModAuthorizationView(
            public_id="test123",
            status=PurgeStatus.PENDING,
            button_style=discord.ButtonStyle.primary,
        )

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.style == discord.ButtonStyle.primary

    async def test_authorize_button_custom_id(self) -> None:
        """Test that the authorize button ID is correct."""
        view = ModAuthorizationView(public_id="test456", status=PurgeStatus.PENDING)

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.custom_id == "purge:authorize:test456"

    async def test_cancel_button_custom_id(self) -> None:
        """Test that the cancel button ID is correct."""
        view = ModAuthorizationView(public_id="test456", status=PurgeStatus.AUTHORIZED)

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.custom_id == "purge:cancel:test456"

    async def test_cancel_button_style_is_danger(self) -> None:
        """Test that the cancel button is always red."""
        view = ModAuthorizationView(
            public_id="test123",
            status=PurgeStatus.AUTHORIZED,
            button_style=discord.ButtonStyle.primary,  # Does not affect cancel
        )

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.style == discord.ButtonStyle.danger


class TestUserConfirmationView:
    """Tests for UserConfirmationView."""

    async def test_view_creation(self) -> None:
        """Test view creation."""
        view = UserConfirmationView(public_id="test123")

        assert view.timeout is None
        assert len(view.children) == 1

    async def test_view_custom_label(self) -> None:
        """Test view with custom label."""
        view = UserConfirmationView(
            public_id="test123",
            confirm_label="Custom Confirm",
        )

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.label == "Custom Confirm"

    async def test_view_custom_button_style(self) -> None:
        """Test view with custom button style."""
        view = UserConfirmationView(
            public_id="test123",
            button_style=discord.ButtonStyle.primary,
        )

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.style == discord.ButtonStyle.primary

    async def test_button_custom_id(self) -> None:
        """Test that the button ID is correct."""
        view = UserConfirmationView(public_id="test789")

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.custom_id == "purge:confirm:test789"
