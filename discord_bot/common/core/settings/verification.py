"""Configuración de verificación."""

from pydantic import BaseModel, ConfigDict, Field


class VerificationSettings(BaseModel):
    """Configuración para el servicio de verificación externa."""

    api_url: str = Field(
        description="URL del endpoint de la API de verificación (vacío para desactivar)",
        default="",
    )
    api_key: str = Field(
        description="Clave de API para autenticación (se envía como X-API-Key header)",
        default="",
    )
    api_timeout: int = Field(
        description="Timeout en segundos para llamadas a la API",
        default=30,
        gt=0,
        le=120,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "api_url": "https://api.example.com/verify",
                "api_key": "your-api-key",
                "api_timeout": 30,
            }
        },
    )
