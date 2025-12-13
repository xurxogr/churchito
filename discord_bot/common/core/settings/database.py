"""Configuración de la base de datos."""

from pydantic import BaseModel, ConfigDict, Field


class DatabaseSettings(BaseModel):
    """Configuración para la base de datos."""

    url: str = Field(
        description="URL de la base de datos",
        default="sqlite+aiosqlite:///data/bot.db",
    )
    echo: bool = Field(description="Mostrar declaraciones SQL", default=False)
    pool_recycle: int = Field(description="Tiempo de reciclaje del pool en segundos", default=3600)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "url": "sqlite+aiosqlite:///data/bot.db",
                "echo": False,
                "pool_recycle": 3600,
            }
        },
    )
