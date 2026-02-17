"""Vista de confirmación para usuarios.

Los botones de esta vista no tienen callbacks propios.
Las interacciones son manejadas por el listener on_interaction del cog,
lo que permite que funcionen incluso despues de reiniciar el bot.
"""

import discord


class ConfirmButton(discord.ui.Button["UserConfirmationView"]):
    """Botón para confirmar permanencia."""

    def __init__(
        self,
        purga_id: int,
        label: str = "Confirmar permanencia",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Inicializar el botón de confirmar.

        Args:
            purga_id (int): ID del registro de purga.
            label (str): Texto del botón.
            style (discord.ButtonStyle): Estilo del botón.
        """
        super().__init__(
            label=label,
            style=style,
            custom_id=f"purga:confirm:{purga_id}",
        )


class UserConfirmationView(discord.ui.View):
    """Vista con botón de confirmación para usuarios.

    Esta vista se adjunta a los mensajes de purga en el canal
    de usuarios.
    """

    def __init__(
        self,
        purga_id: int,
        confirm_label: str = "Confirmar permanencia",
        button_style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Inicializar la vista de confirmación.

        Args:
            purga_id (int): ID del registro de purga.
            confirm_label (str): Texto del botón de confirmar.
            button_style (discord.ButtonStyle): Estilo del botón.
        """
        super().__init__(timeout=None)
        self.purga_id = purga_id

        self.add_item(ConfirmButton(purga_id=purga_id, label=confirm_label, style=button_style))
