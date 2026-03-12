"""Vista de seleccion de motivo de rechazo."""

import discord

from discord_bot.verification.views.protocols import get_verification_cog
from discord_bot.verification.views.rejection_modal import RejectionReasonModal


class ReasonSelect(discord.ui.Select["RejectionReasonView"]):
    """Selector de motivos de rechazo."""

    def __init__(
        self,
        public_id: str,
        options: list[discord.SelectOption],
        placeholder: str,
        modal_title: str,
        modal_label: str,
        modal_placeholder: str,
    ) -> None:
        """Inicializar el selector.

        Args:
            public_id (str): ID público de la solicitud de verificacion (NanoID)
            options (list[discord.SelectOption]): Opciones del selector
            placeholder (str): Texto del placeholder
            modal_title (str): Titulo del modal de motivo personalizado
            modal_label (str): Etiqueta del campo de texto del modal
            modal_placeholder (str): Placeholder del campo de texto del modal
        """
        super().__init__(
            placeholder=placeholder,
            options=options,
            custom_id=f"verification:reject_reason:{public_id}",
        )
        self.public_id = public_id
        self.modal_title = modal_title
        self.modal_label = modal_label
        self.modal_placeholder = modal_placeholder

    async def callback(self, interaction: discord.Interaction[discord.Client]) -> None:
        """Manejar seleccion de motivo de rechazo.

        Args:
            interaction (discord.Interaction[discord.Client]): Interaccion del moderador
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
            cog = get_verification_cog(interaction)
            if cog:
                await cog.handle_reject(
                    interaction=interaction,
                    public_id=self.public_id,
                    reason=selected,
                )

        if self.view:
            self.view.stop()


class RejectionReasonView(discord.ui.View):
    """Vista con dropdown para seleccionar motivo de rechazo.

    Muestra opciones predefinidas configurables mas una opcion "Otro"
    que abre el modal para texto personalizado.
    """

    def __init__(
        self,
        public_id: str,
        reasons: list[str],
        other_label: str = "Otro motivo...",
        other_description: str = "Escribir un motivo personalizado",
        placeholder: str = "Selecciona el motivo de rechazo...",
        modal_title: str = "Motivo de Rechazo",
        modal_label: str = "Motivo",
        modal_placeholder: str = "Explica por que se rechaza la verificacion...",
    ) -> None:
        """Inicializar la vista de seleccion.

        Args:
            public_id (str): ID público de la solicitud de verificacion (NanoID)
            reasons (list[str]): Lista de motivos predefinidos
            other_label (str): Etiqueta para la opcion "Otro"
            other_description (str): Descripcion para la opcion "Otro"
            placeholder (str): Texto del placeholder del selector
            modal_title (str): Titulo del modal de motivo personalizado
            modal_label (str): Etiqueta del campo de texto del modal
            modal_placeholder (str): Placeholder del campo de texto del modal
        """
        super().__init__(timeout=60)

        options = [
            discord.SelectOption(label=reason[:100], value=reason[:100])
            for reason in reasons
            if reason.strip()
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
                placeholder=placeholder,
                modal_title=modal_title,
                modal_label=modal_label,
                modal_placeholder=modal_placeholder,
            )
        )
