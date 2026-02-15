"""Modal para motivo de rechazo."""

import discord

from discord_bot.verification.views.protocols import get_verification_cog


class RejectionReasonModal(discord.ui.Modal):
    """Modal para ingresar el motivo de rechazo."""

    def __init__(
        self,
        request_id: int,
        title: str = "Motivo de Rechazo",
        label: str = "Motivo",
        placeholder: str = "Explica por que se rechaza la verificacion...",
    ) -> None:
        """Inicializar el modal.

        Args:
            request_id (int): ID de la solicitud de verificacion
            title (str): Titulo del modal
            label (str): Etiqueta del campo de texto
            placeholder (str): Texto de ayuda del campo
        """
        super().__init__(title=title)
        self.request_id = request_id

        self.reason: discord.ui.TextInput[RejectionReasonModal] = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Procesar envio del modal.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.handle_reject(
            interaction=interaction,
            request_id=self.request_id,
            reason=self.reason.value,
        )
