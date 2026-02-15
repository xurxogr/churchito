"""Vista del panel de verificacion."""

import discord

from discord_bot.verification.enums import VerificationType
from discord_bot.verification.views.protocols import get_verification_cog


class VerificationButton(discord.ui.Button["VerificationPanelView"]):
    """Boton de verificacion con tipo configurable."""

    def __init__(
        self,
        label: str,
        verification_type: VerificationType,
        style: discord.ButtonStyle,
        custom_id: str,
    ) -> None:
        """Inicializar el boton de verificacion.

        Args:
            label (str): Texto del boton
            verification_type (VerificationType): Tipo de verificacion
            style (discord.ButtonStyle): Estilo del boton
            custom_id (str): ID unico del boton
        """
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.verification_type = verification_type

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Manejar clic en boton de verificacion.

        Args:
            interaction (discord.Interaction[discord.Client]): Interaccion del usuario
        """
        cog = get_verification_cog(interaction)
        if not cog:
            return

        await cog.handle_verification_start(
            interaction=interaction, verification_type=self.verification_type
        )


class VerificationPanelView(discord.ui.View):
    """Vista persistente con botones de verificacion.

    Esta vista se muestra en el canal de verificacion y permite
    a los usuarios iniciar el proceso de verificacion.
    """

    def __init__(
        self,
        verify_label: str = "Verificar",
        ally_label: str = "Verificar como Aliado",
    ) -> None:
        """Inicializar la vista del panel.

        Args:
            verify_label (str): Texto del boton de verificacion normal
            ally_label (str): Texto del boton de verificacion de aliado
        """
        super().__init__(timeout=None)

        self.add_item(
            VerificationButton(
                label=verify_label,
                verification_type=VerificationType.REGULAR,
                style=discord.ButtonStyle.primary,
                custom_id=f"verification:{VerificationType.REGULAR}",
            )
        )
        self.add_item(
            VerificationButton(
                label=ally_label,
                verification_type=VerificationType.ALLY,
                style=discord.ButtonStyle.secondary,
                custom_id=f"verification:{VerificationType.ALLY}",
            )
        )
