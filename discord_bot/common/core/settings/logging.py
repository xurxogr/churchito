"""Configuración de log."""

from pydantic import BaseModel, ConfigDict, Field


class LoggingSettings(BaseModel):
    """Configuración para el log."""

    loggers: dict[str, str] = Field(description="Registradores y sus niveles", default_factory=dict)
    log_level: str = Field(description="Nivel de log", default="INFO")
    log_format: str = Field(
        description="Formato de log",
        default="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    )
    date_format: str = Field(description="Formato de fecha de log", default="%Y-%m-%d %H:%M:%S")
    rotate_logs: bool = Field(description="Rotar logs diariamente", default=False)
    log_file: str | None = Field(description="Archivo de log en el que escribir", default=None)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "loggers": {"discord_bot": "DEBUG", "discord": "INFO"},
                "log_level": "INFO",
                "log_format": "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
                "date_format": "%Y-%m-%d %H:%M:%S",
                "rotate_logs": False,
                "log_file": None,
            }
        },
    )
