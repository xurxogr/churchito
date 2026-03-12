"""Vista de revision para moderadores.

Los botones de esta vista no tienen callbacks propios.
Las interacciones son manejadas por el listener on_interaction del cog,
lo que permite que funcionen incluso despues de reiniciar el bot.
"""

import discord


class AcceptButton(discord.ui.Button["ModReviewView"]):
    """Boton para aceptar una solicitud de verificacion."""

    def __init__(self, public_id: str, label: str = "Aceptar") -> None:
        """Inicializar el boton de aceptar.

        Args:
            public_id (str): ID público de la solicitud de verificacion (NanoID)
            label (str): Texto del boton
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"verification:accept:{public_id}",
        )


class RejectButton(discord.ui.Button["ModReviewView"]):
    """Boton para rechazar una solicitud de verificacion."""

    def __init__(self, public_id: str, label: str = "Rechazar") -> None:
        """Inicializar el boton de rechazar.

        Args:
            public_id (str): ID público de la solicitud de verificacion (NanoID)
            label (str): Texto del boton
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"verification:reject:{public_id}",
        )


class ModReviewView(discord.ui.View):
    """Vista con botones de aceptar/rechazar para moderadores.

    Esta vista se adjunta a los mensajes de revision en el canal
    de moderacion.
    """

    def __init__(
        self,
        public_id: str,
        accept_label: str = "Aceptar",
        reject_label: str = "Rechazar",
    ) -> None:
        """Inicializar la vista de revision.

        Args:
            public_id (str): ID público de la solicitud de verificacion (NanoID)
            accept_label (str): Texto del boton de aceptar
            reject_label (str): Texto del boton de rechazar
        """
        super().__init__(timeout=None)
        self.public_id = public_id

        self.add_item(AcceptButton(public_id=public_id, label=accept_label))
        self.add_item(RejectButton(public_id=public_id, label=reject_label))
