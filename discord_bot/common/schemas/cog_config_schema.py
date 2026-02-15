"""Esquema de configuración de un cog."""

import copy

from pydantic import BaseModel, Field

from discord_bot.common.schemas.config_option import ConfigOption


class CogConfigSchema(BaseModel):
    """Esquema completo de configuración para un cog.

    Este modelo representa el esquema de configuración de un cog,
    incluyendo metadatos del cog y la lista de opciones configurables.
    """

    cog_name: str = Field(description="Identificador único del cog")
    display_name: str = Field(description="Nombre legible para mostrar en la UI")
    description: str = Field(default="", description="Descripción del cog")
    icon: str = Field(default="", description="Emoji o icono para mostrar en la UI")
    options: list[ConfigOption] = Field(
        default_factory=list, description="Lista de opciones configurables"
    )

    def get_option(self, key: str) -> ConfigOption | None:
        """Obtener una opción de configuración por su clave.

        Args:
            key (str): Clave de la opción a buscar

        Returns:
            ConfigOption | None: La opción si existe, None en caso contrario
        """
        for option in self.options:
            if option.key == key:
                return option
        return None

    def get_default_values(self) -> dict[str, object]:
        """Obtener un diccionario con los valores por defecto de todas las opciones.

        Returns:
            dict[str, object]: Diccionario con clave -> valor_default
        """
        return {option.key: copy.deepcopy(option.default) for option in self.options}
