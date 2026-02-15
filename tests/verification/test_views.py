"""Tests para las vistas de verificacion."""

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
    """Tests para VerificationPanelView."""

    async def test_init_default_labels(self) -> None:
        """Probar inicializacion con labels por defecto."""
        view = VerificationPanelView()

        assert len(view.children) == 2
        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].label == "Verificar"
        assert buttons[1].label == "Verificar como Aliado"

    async def test_init_custom_labels(self) -> None:
        """Probar inicializacion con labels personalizados."""
        view = VerificationPanelView(verify_label="Custom Verify", ally_label="Custom Ally")

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].label == "Custom Verify"
        assert buttons[1].label == "Custom Ally"

    async def test_button_custom_ids(self) -> None:
        """Probar que los botones tienen custom_id correcto."""
        view = VerificationPanelView()

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].custom_id == "verification:regular"
        assert buttons[1].custom_id == "verification:ally"

    async def test_button_styles(self) -> None:
        """Probar estilos de botones."""
        view = VerificationPanelView()

        buttons = [child for child in view.children if isinstance(child, VerificationButton)]
        assert buttons[0].style == discord.ButtonStyle.primary
        assert buttons[1].style == discord.ButtonStyle.secondary

    async def test_regular_button_callback(self) -> None:
        """Probar callback del boton regular."""
        view = VerificationPanelView()

        # Mock interaction y bot
        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_verification_start = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        # Obtener el boton y llamar su callback
        regular_button = view.children[0]
        await regular_button.callback(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")
        mock_cog.handle_verification_start.assert_called_once_with(
            interaction=interaction, verification_type="regular"
        )

    async def test_ally_button_callback(self) -> None:
        """Probar callback del boton aliado."""
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
        """Probar callback cuando el cog no existe."""
        view = VerificationPanelView()

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        # No deberia fallar
        regular_button = view.children[0]
        await regular_button.callback(interaction)


class TestModReviewView:
    """Tests para ModReviewView."""

    async def test_init_default_labels(self) -> None:
        """Probar inicializacion con labels por defecto."""
        view = ModReviewView(request_id=123)

        assert len(view.children) == 2
        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.label == "Aceptar"
        assert reject_btn.label == "Rechazar"

    async def test_init_custom_labels(self) -> None:
        """Probar inicializacion con labels personalizados."""
        view = ModReviewView(request_id=123, accept_label="Aprobar", reject_label="Denegar")

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.label == "Aprobar"
        assert reject_btn.label == "Denegar"

    async def test_button_custom_ids(self) -> None:
        """Probar que los botones tienen custom_id con request_id."""
        view = ModReviewView(request_id=456)

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.custom_id == "verification:accept:456"
        assert reject_btn.custom_id == "verification:reject:456"

    async def test_button_styles(self) -> None:
        """Probar estilos de botones."""
        view = ModReviewView(request_id=123)

        accept_btn = next(c for c in view.children if isinstance(c, AcceptButton))
        reject_btn = next(c for c in view.children if isinstance(c, RejectButton))
        assert accept_btn.style == discord.ButtonStyle.success
        assert reject_btn.style == discord.ButtonStyle.danger

    # Los botones no tienen callbacks propios.
    # Las interacciones son manejadas por on_interaction del cog.


class TestRejectionReasonView:
    """Tests para RejectionReasonView."""

    async def test_init_creates_select(self) -> None:
        """Probar que se crea el selector."""
        reasons = ["Motivo 1", "Motivo 2"]
        view = RejectionReasonView(request_id=123, reasons=reasons)

        assert len(view.children) == 1
        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert isinstance(select, discord.ui.Select)

    async def test_select_options(self) -> None:
        """Probar opciones del selector."""
        reasons = ["Motivo 1", "Motivo 2"]
        view = RejectionReasonView(request_id=123, reasons=reasons)

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # 2 motivos + "Otro motivo..."
        assert len(select.options) == 3
        assert select.options[0].label == "Motivo 1"
        assert select.options[1].label == "Motivo 2"
        assert select.options[2].value == "__OTHER__"

    async def test_select_custom_id(self) -> None:
        """Probar custom_id del selector."""
        view = RejectionReasonView(request_id=456, reasons=["Motivo"])

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert select.custom_id == "verification:reject_reason:456"

    async def test_ignores_empty_reasons(self) -> None:
        """Probar que ignora motivos vacios."""
        reasons = ["Motivo 1", "", "  ", "Motivo 2"]
        view = RejectionReasonView(request_id=123, reasons=reasons)

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # Solo 2 motivos validos + "Otro"
        assert len(select.options) == 3

    async def test_truncates_long_reasons(self) -> None:
        """Probar que trunca motivos largos a 100 caracteres."""
        long_reason = "A" * 150
        view = RejectionReasonView(request_id=123, reasons=[long_reason])

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        assert len(select.options[0].label) == 100

    async def test_select_predefined_reason_callback(self) -> None:
        """Probar callback con motivo predefinido."""
        view = RejectionReasonView(request_id=789, reasons=["Motivo test"])

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_reject = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        # Set the internal values list directly
        object.__setattr__(select, "_values", ["Motivo test"])

        await select.callback(interaction)

        mock_cog.handle_reject.assert_called_once_with(
            interaction=interaction, request_id=789, reason="Motivo test"
        )

    async def test_select_other_reason_callback(self) -> None:
        """Probar callback con 'Otro motivo'."""
        view = RejectionReasonView(request_id=789, reasons=["Motivo"])

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
        """Probar callback con motivo predefinido cuando el cog no existe."""
        view = RejectionReasonView(request_id=789, reasons=["Motivo test"])

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        select = next(c for c in view.children if isinstance(c, ReasonSelect))
        object.__setattr__(select, "_values", ["Motivo test"])

        # No deberia fallar, solo retornar temprano
        await select.callback(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")


class TestRejectionReasonModal:
    """Tests para RejectionReasonModal."""

    async def test_init(self) -> None:
        """Probar inicializacion del modal."""
        modal = RejectionReasonModal(request_id=123)

        assert modal.request_id == 123
        assert modal.title == "Motivo de Rechazo"

    async def test_has_text_input(self) -> None:
        """Probar que tiene un campo de texto."""
        modal = RejectionReasonModal(request_id=123)

        # El modal tiene children (TextInput)
        assert len(modal.children) == 1

    async def test_on_submit_calls_handle_reject(self) -> None:
        """Probar que on_submit llama a handle_reject."""
        modal = RejectionReasonModal(request_id=789)

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        mock_cog = MagicMock()
        mock_cog.handle_reject = AsyncMock()
        bot.get_cog.return_value = mock_cog
        interaction.client = bot

        # Simular valor del TextInput usando mock
        modal.reason = MagicMock()
        modal.reason.value = "Motivo personalizado"

        await modal.on_submit(interaction)

        mock_cog.handle_reject.assert_called_once_with(
            interaction=interaction, request_id=789, reason="Motivo personalizado"
        )

    async def test_on_submit_no_cog(self) -> None:
        """Probar on_submit cuando el cog no existe."""
        modal = RejectionReasonModal(request_id=789)

        interaction = MagicMock(spec=discord.Interaction)
        bot = MagicMock(spec=commands.Bot)
        bot.get_cog.return_value = None
        interaction.client = bot

        modal.reason = MagicMock()
        modal.reason.value = "Motivo personalizado"

        # No deberia fallar, solo retornar temprano
        await modal.on_submit(interaction)

        bot.get_cog.assert_called_once_with("VerificationCog")
