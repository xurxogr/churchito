"""Vista de revisión para auto-rechazos.

Permite a los moderadores revisar verificaciones que fueron
auto-rechazadas dentro de la ventana de tiempo configurada.
"""

import discord


class ReviewButton(discord.ui.Button["AutoRejectReviewView"]):
    """Botón para revisar un auto-rechazo."""

    def __init__(self, request_id: int, label: str = "Revisar") -> None:
        """Inicializar el botón de revisar.

        Args:
            request_id (int): ID de la solicitud de verificación
            label (str): Texto del botón
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"verification:review:{request_id}",
        )


class AutoRejectReviewView(discord.ui.View):
    """Vista con botón de revisar para auto-rechazos.

    Esta vista se adjunta a los mensajes de auto-rechazo durante
    la ventana de tiempo configurada.
    """

    def __init__(
        self,
        request_id: int,
        review_label: str = "Revisar",
        timeout_minutes: int = 30,
    ) -> None:
        """Inicializar la vista de revisión.

        Args:
            request_id (int): ID de la solicitud de verificación
            review_label (str): Texto del botón de revisar
            timeout_minutes (int): Minutos hasta que el botón expire
        """
        # Convertir minutos a segundos para el timeout
        timeout_seconds = timeout_minutes * 60 if timeout_minutes > 0 else None
        super().__init__(timeout=timeout_seconds)
        self.request_id = request_id

        self.add_item(ReviewButton(request_id=request_id, label=review_label))
