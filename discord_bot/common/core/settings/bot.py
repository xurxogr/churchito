"""Configuración sobre Bot."""

from pydantic import BaseModel, ConfigDict, Field


class BotSettings(BaseModel):
    """Configuración para bot de Discord."""

    token: str = Field(description="Token del bot de Discord", default="")
    command_prefix: str = Field(description="Prefijo de comandos", default="!")
    owner_id: int | None = Field(description="ID de usuario del propietario del bot", default=None)
    description: str = Field(
        description="Descripción del bot",
        default="Un bot de Discord con arquitectura basada en cogs",
    )
    event_loop_warning_threshold: float = Field(
        description="Umbral de advertencia para retrasos en el bucle de eventos (en segundos)",
        default=0.5,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "token": "TU_TOKEN_DEL_BOT",
                "command_prefix": "!",
                "owner_id": None,
                "description": "Un bot de Discord con arquitectura basada en cogs",
                "event_loop_warning_threshold": 0.5,
            }
        },
    )
