"""Servicio para registro de esquemas de configuración de cogs."""

import logging
from functools import lru_cache

from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption

logger = logging.getLogger(__name__)


class ConfigSchemaService:
    """Servicio en memoria para registro y consulta de esquemas de configuración.

    Este servicio mantiene en memoria los esquemas de configuración registrados
    por cada cog. No tiene dependencias de base de datos - solo almacena
    los metadatos de las opciones de configuración disponibles.
    """

    def __init__(self) -> None:
        """Inicializar el servicio de esquemas de configuración."""
        self._schemas: dict[str, CogConfigSchema] = {}

    def register_schema(self, schema: CogConfigSchema) -> None:
        """Registrar el esquema de configuración de un cog.

        Args:
            schema (CogConfigSchema): Esquema de configuración a registrar
        """
        if schema.cog_name in self._schemas:
            logger.warning(f"Sobrescribiendo esquema existente para cog '{schema.cog_name}'")
        self._schemas[schema.cog_name] = schema
        logger.info(
            f"Esquema de configuración registrado para cog '{schema.cog_name}' "
            f"con {len(schema.options)} opciones"
        )

    def unregister_schema(self, cog_name: str) -> bool:
        """Desregistrar el esquema de configuración de un cog.

        Args:
            cog_name (str): Nombre del cog a desregistrar

        Returns:
            bool: True si se desregistró, False si no existía
        """
        if cog_name in self._schemas:
            del self._schemas[cog_name]
            logger.info(f"Esquema de configuración desregistrado para cog '{cog_name}'")
            return True
        return False

    def get_schema(self, cog_name: str) -> CogConfigSchema | None:
        """Obtener el esquema de configuración de un cog.

        Args:
            cog_name (str): Nombre del cog

        Returns:
            CogConfigSchema | None: Esquema si existe, None en caso contrario
        """
        return self._schemas.get(cog_name)

    def get_all_schemas(self) -> dict[str, CogConfigSchema]:
        """Obtener todos los esquemas de configuración registrados.

        Returns:
            dict[str, CogConfigSchema]: Diccionario de todos los esquemas
        """
        return self._schemas.copy()

    def get_option(self, cog_name: str, key: str) -> ConfigOption | None:
        """Obtener una opción de configuración específica.

        Args:
            cog_name (str): Nombre del cog
            key (str): Clave de la opción

        Returns:
            ConfigOption | None: La opción si existe, None en caso contrario
        """
        schema = self.get_schema(cog_name)
        if schema:
            return schema.get_option(key)
        return None

    def has_schema(self, cog_name: str) -> bool:
        """Verificar si existe un esquema para un cog.

        Args:
            cog_name (str): Nombre del cog

        Returns:
            bool: True si existe el esquema
        """
        return cog_name in self._schemas

    def get_cog_names(self) -> list[str]:
        """Obtener la lista de nombres de cogs con esquemas registrados.

        Returns:
            list[str]: Lista de nombres de cogs
        """
        return list(self._schemas.keys())


@lru_cache
def get_config_schema_service() -> ConfigSchemaService:
    """Obtener el singleton del servicio de esquemas de configuración.

    Returns:
        ConfigSchemaService: Instancia del servicio
    """
    return ConfigSchemaService()
