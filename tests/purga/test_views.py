"""Tests para vistas de purga."""

import discord

from discord_bot.purga.enums import PurgaStatus
from discord_bot.purga.views import ModAuthorizationView, UserConfirmationView
from discord_bot.purga.views.mod_authorization import AuthorizeButton, CancelButton
from discord_bot.purga.views.user_confirmation import ConfirmButton


class TestModAuthorizationView:
    """Tests para ModAuthorizationView."""

    async def test_view_creation_pending(self) -> None:
        """Probar creación de vista con estado PENDING."""
        view = ModAuthorizationView(purga_id=123, status=PurgaStatus.PENDING)

        assert view.purga_id == 123
        assert view.status == PurgaStatus.PENDING
        assert view.timeout is None
        assert len(view.children) == 1
        assert isinstance(view.children[0], AuthorizeButton)

    async def test_view_creation_authorized(self) -> None:
        """Probar creación de vista con estado AUTHORIZED."""
        view = ModAuthorizationView(purga_id=123, status=PurgaStatus.AUTHORIZED)

        assert view.purga_id == 123
        assert view.status == PurgaStatus.AUTHORIZED
        assert view.timeout is None
        assert len(view.children) == 1
        assert isinstance(view.children[0], CancelButton)

    async def test_view_custom_authorize_label(self) -> None:
        """Probar vista con etiqueta personalizada de autorizar."""
        view = ModAuthorizationView(
            purga_id=123,
            status=PurgaStatus.PENDING,
            authorize_label="Custom Authorize",
        )

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.label == "Custom Authorize"

    async def test_view_custom_cancel_label(self) -> None:
        """Probar vista con etiqueta personalizada de cancelar."""
        view = ModAuthorizationView(
            purga_id=123,
            status=PurgaStatus.AUTHORIZED,
            cancel_label="Custom Cancel",
        )

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.label == "Custom Cancel"

    async def test_view_custom_button_style(self) -> None:
        """Probar vista con estilo de botón personalizado."""
        view = ModAuthorizationView(
            purga_id=123,
            status=PurgaStatus.PENDING,
            button_style=discord.ButtonStyle.primary,
        )

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.style == discord.ButtonStyle.primary

    async def test_authorize_button_custom_id(self) -> None:
        """Probar que el ID del botón de autorizar es correcto."""
        view = ModAuthorizationView(purga_id=456, status=PurgaStatus.PENDING)

        authorize_btn = next(c for c in view.children if isinstance(c, AuthorizeButton))
        assert authorize_btn.custom_id == "purga:authorize:456"

    async def test_cancel_button_custom_id(self) -> None:
        """Probar que el ID del botón de cancelar es correcto."""
        view = ModAuthorizationView(purga_id=456, status=PurgaStatus.AUTHORIZED)

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.custom_id == "purga:cancel:456"

    async def test_cancel_button_style_is_danger(self) -> None:
        """Probar que el botón de cancelar siempre es rojo."""
        view = ModAuthorizationView(
            purga_id=123,
            status=PurgaStatus.AUTHORIZED,
            button_style=discord.ButtonStyle.primary,  # No afecta cancel
        )

        cancel_btn = next(c for c in view.children if isinstance(c, CancelButton))
        assert cancel_btn.style == discord.ButtonStyle.danger


class TestUserConfirmationView:
    """Tests para UserConfirmationView."""

    async def test_view_creation(self) -> None:
        """Probar creación de vista."""
        view = UserConfirmationView(purga_id=123)

        assert view.purga_id == 123
        assert view.timeout is None
        assert len(view.children) == 1

    async def test_view_custom_label(self) -> None:
        """Probar vista con etiqueta personalizada."""
        view = UserConfirmationView(
            purga_id=123,
            confirm_label="Custom Confirm",
        )

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.label == "Custom Confirm"

    async def test_view_custom_button_style(self) -> None:
        """Probar vista con estilo de botón personalizado."""
        view = UserConfirmationView(
            purga_id=123,
            button_style=discord.ButtonStyle.primary,
        )

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.style == discord.ButtonStyle.primary

    async def test_button_custom_id(self) -> None:
        """Probar que el ID de botón es correcto."""
        view = UserConfirmationView(purga_id=789)

        button = next(c for c in view.children if isinstance(c, ConfirmButton))
        assert button.custom_id == "purga:confirm:789"
