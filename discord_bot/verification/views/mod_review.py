"""Vista de revision para moderadores."""

import discord

from discord_bot.verification.views.protocols import get_verification_cog


class AcceptButton(discord.ui.Button["ModReviewView"]):
    """Boton para aceptar una solicitud de verificacion."""

    def __init__(self, request_id: int, label: str = "Aceptar") -> None:
        """Inicializar el boton de aceptar.

        Args:
            request_id (int): ID de la solicitud de verificacion
            label (str): Texto del boton
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"verification:accept:{request_id}",
        )
        self.request_id = request_id

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Manejar clic en boton de aceptar.

        Args:
            interaction (discord.Interaction[discord.Client]): Interaccion del moderador
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.handle_accept(interaction=interaction, request_id=self.request_id)


class RejectButton(discord.ui.Button["ModReviewView"]):
    """Boton para rechazar una solicitud de verificacion."""

    def __init__(self, request_id: int, label: str = "Rechazar") -> None:
        """Inicializar el boton de rechazar.

        Args:
            request_id (int): ID de la solicitud de verificacion
            label (str): Texto del boton
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"verification:reject:{request_id}",
        )
        self.request_id = request_id

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Manejar clic en boton de rechazar.

        Args:
            interaction (discord.Interaction[discord.Client]): Interaccion del moderador
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.show_rejection_select(interaction=interaction, request_id=self.request_id)


class ModReviewView(discord.ui.View):
    """Vista con botones de aceptar/rechazar para moderadores.

    Esta vista se adjunta a los mensajes de revision en el canal
    de moderacion.
    """

    def __init__(
        self,
        request_id: int,
        accept_label: str = "Aceptar",
        reject_label: str = "Rechazar",
    ) -> None:
        """Inicializar la vista de revision.

        Args:
            request_id (int): ID de la solicitud de verificacion
            accept_label (str): Texto del boton de aceptar
            reject_label (str): Texto del boton de rechazar
        """
        super().__init__(timeout=None)
        self.request_id = request_id

        self.add_item(AcceptButton(request_id=request_id, label=accept_label))
        self.add_item(RejectButton(request_id=request_id, label=reject_label))
