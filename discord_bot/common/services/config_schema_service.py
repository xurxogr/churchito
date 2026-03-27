"""Service for registering cog configuration schemas."""

import logging
from functools import lru_cache

from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption

logger = logging.getLogger(__name__)


class ConfigSchemaService:
    """In-memory service for registering and querying configuration schemas.

    This service maintains in memory the configuration schemas registered
    by each cog. It has no database dependencies - it only stores
    the metadata of available configuration options.
    """

    def __init__(self) -> None:
        """Initialize the configuration schema service."""
        self._schemas: dict[str, CogConfigSchema] = {}

    def register_schema(self, schema: CogConfigSchema) -> None:
        """Register a cog's configuration schema.

        Args:
            schema (CogConfigSchema): Configuration schema to register
        """
        if schema.cog_name in self._schemas:
            logger.warning(f"Overwriting existing schema for cog '{schema.cog_name}'")
        self._schemas[schema.cog_name] = schema
        logger.info(
            f"Configuration schema registered for cog '{schema.cog_name}' "
            f"with {len(schema.options)} options"
        )

    def unregister_schema(self, cog_name: str) -> bool:
        """Unregister a cog's configuration schema.

        Args:
            cog_name (str): Name of the cog to unregister

        Returns:
            bool: True if unregistered, False if it didn't exist
        """
        if cog_name in self._schemas:
            del self._schemas[cog_name]
            logger.info(f"Configuration schema unregistered for cog '{cog_name}'")
            return True
        return False

    def get_schema(self, cog_name: str) -> CogConfigSchema | None:
        """Get a cog's configuration schema.

        Args:
            cog_name (str): Name of the cog

        Returns:
            CogConfigSchema | None: Schema if it exists, None otherwise
        """
        return self._schemas.get(cog_name)

    def get_all_schemas(self) -> dict[str, CogConfigSchema]:
        """Get all registered configuration schemas.

        Returns:
            dict[str, CogConfigSchema]: Dictionary of all schemas
        """
        return self._schemas.copy()

    def get_option(self, cog_name: str, key: str) -> ConfigOption | None:
        """Get a specific configuration option.

        Args:
            cog_name (str): Name of the cog
            key (str): Option key

        Returns:
            ConfigOption | None: The option if it exists, None otherwise
        """
        schema = self.get_schema(cog_name)
        if schema:
            return schema.get_option(key)
        return None

    def has_schema(self, cog_name: str) -> bool:
        """Check if a schema exists for a cog.

        Args:
            cog_name (str): Name of the cog

        Returns:
            bool: True if the schema exists
        """
        return cog_name in self._schemas

    def get_cog_names(self) -> list[str]:
        """Get the list of cog names with registered schemas.

        Returns:
            list[str]: List of cog names
        """
        return list(self._schemas.keys())


@lru_cache
def get_config_schema_service() -> ConfigSchemaService:
    """Get the configuration schema service singleton.

    Returns:
        ConfigSchemaService: Service instance
    """
    return ConfigSchemaService()
