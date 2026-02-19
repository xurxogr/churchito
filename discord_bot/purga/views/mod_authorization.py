"""Vista de autorización para moderadores.

Los botones de esta vista no tienen callbacks propios.
Las interacciones son manejadas por el listener on_interaction del cog,
lo que permite que funcionen incluso despues de reiniciar el bot.
"""

import discord

from discord_bot.purga.enums import PurgaStatus


class AuthorizeButton(discord.ui.Button["ModAuthorizationView"]):
    """Botón para autorizar una purga."""

    def __init__(
        self,
        purga_id: int,
        label: str = "Autorizar purga",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Inicializar el botón de autorizar.

        Args:
            purga_id (int): ID del registro de purga.
            label (str): Texto del botón.
            style (discord.ButtonStyle): Estilo del botón.
        """
        super().__init__(
            label=label,
            style=style,
            custom_id=f"purga:authorize:{purga_id}",
        )


class CancelButton(discord.ui.Button["ModAuthorizationView"]):
    """Botón para cancelar una purga."""

    def __init__(
        self,
        purga_id: int,
        label: str = "Detener purga",
    ) -> None:
        """Inicializar el botón de cancelar.

        Args:
            purga_id (int): ID del registro de purga.
            label (str): Texto del botón.
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"purga:cancel:{purga_id}",
        )


class ModAuthorizationView(discord.ui.View):
    """Vista con botones de autorizar/cancelar para moderadores.

    Esta vista se adjunta a los mensajes de autorización en el canal
    de moderación. Los botones mostrados dependen del estado de la purga:
    - PENDING: Muestra botón de autorizar
    - AUTHORIZED: Muestra botón de cancelar/detener
    """

    def __init__(
        self,
        purga_id: int,
        status: PurgaStatus,
        authorize_label: str = "Autorizar purga",
        cancel_label: str = "Detener purga",
        button_style: discord.ButtonStyle = discord.ButtonStyle.success,
    ) -> None:
        """Inicializar la vista de autorización.

        Args:
            purga_id (int): ID del registro de purga.
            status (PurgaStatus): Estado actual de la purga.
            authorize_label (str): Texto del botón de autorizar.
            cancel_label (str): Texto del botón de cancelar.
            button_style (discord.ButtonStyle): Estilo del botón de autorizar.
        """
        super().__init__(timeout=None)
        self.purga_id = purga_id
        self.status = status

        if status == PurgaStatus.PENDING:
            self.add_item(
                AuthorizeButton(purga_id=purga_id, label=authorize_label, style=button_style)
            )
        elif status in (PurgaStatus.AUTHORIZED, PurgaStatus.CANCEL_PENDING):
            self.add_item(CancelButton(purga_id=purga_id, label=cancel_label))
