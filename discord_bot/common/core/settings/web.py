"""Configuración del dashboard web."""

from pydantic import BaseModel, ConfigDict, Field


class WebSettings(BaseModel):
    """Configuración para el dashboard web con Discord OAuth."""

    enabled: bool = Field(
        description="Habilitar el dashboard web",
        default=False,
    )
    host: str = Field(
        description="Host para el servidor web",
        default="0.0.0.0",
    )
    port: int = Field(
        description="Puerto para el servidor web",
        default=8000,
    )
    root_path: str = Field(
        description="Ruta base cuando se sirve detrás de un proxy (ej: /bot)",
        default="",
    )
    secret_key: str = Field(
        description="Clave secreta para sesiones (generada automáticamente si está vacía)",
        default="",
    )
    client_id: str = Field(
        description="ID de cliente de la aplicación Discord OAuth",
        default="",
    )
    client_secret: str = Field(
        description="Secreto de cliente de la aplicación Discord OAuth",
        default="",
    )
    redirect_uri: str = Field(
        description="URI de redirección para OAuth (ej: http://localhost:8000/auth/callback)",
        default="http://localhost:8000/auth/callback",
    )
    owner_ids: list[int] = Field(
        description="IDs de usuarios con acceso de administrador al dashboard",
        default_factory=list,
    )
    https_only: bool = Field(
        description="Solo enviar cookie de sesión sobre HTTPS (usar True en producción)",
        default=True,
    )
    session_max_age: int = Field(
        description="Duración máxima de la sesión en segundos (default: 2 horas)",
        default=7200,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8000,
                "root_path": "/bot",
                "secret_key": "tu-clave-secreta-aqui",
                "client_id": "tu-client-id-de-discord",
                "client_secret": "tu-client-secret-de-discord",
                "redirect_uri": "http://localhost:8000/auth/callback",
                "owner_ids": [123456789012345678],
                "https_only": True,
                "session_max_age": 7200,
            }
        },
    )
