"""Service for guild configuration CRUD operations."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.models.guild_cog_enabled import GuildCogEnabled
from discord_bot.common.models.guild_config import GuildConfig
from discord_bot.common.services.config_schema_service import (
    ConfigSchemaService,
    get_config_schema_service,
)

logger = logging.getLogger(__name__)


class ConfigService:
    """Service for database configuration operations.

    This service handles CRUD operations for configuration values
    stored in the database. It uses the ConfigSchemaService for
    validation and default values.
    """

    def __init__(
        self, session: AsyncSession, schema_service: ConfigSchemaService | None = None
    ) -> None:
        """Initialize the configuration service.

        Args:
            session (AsyncSession): Database session
            schema_service (ConfigSchemaService | None): Schema service
                (uses singleton if not provided)
        """
        self._session = session
        self._schema_service = schema_service or get_config_schema_service()

    async def get_value(self, guild_id: int, cog_name: str, key: str) -> Any:
        """Get a configuration value.

        If no stored value exists, returns the default value from the schema.

        Args:
            guild_id (int): Guild ID
            cog_name (str): Cog name
            key (str): Option key

        Returns:
            Any: Configuration value or default value
        """
        result = await self._session.execute(
            select(GuildConfig.value).where(
                GuildConfig.guild_id == guild_id,
                GuildConfig.cog_name == cog_name,
                GuildConfig.key == key,
            )
        )
        row = result.scalar_one_or_none()

        if row is not None:
            return row

        option = self._schema_service.get_option(cog_name, key)
        return option.default if option else None

    async def set_value(
        self, guild_id: int, cog_name: str, key: str, value: Any
    ) -> tuple[bool, str | None]:
        """Set a configuration value.

        Validates the value against the schema before saving.

        Args:
            guild_id (int): Guild ID
            cog_name (str): Cog name
            key (str): Option key
            value (Any): Value to set

        Returns:
            tuple[bool, str | None]: (success, error_message)
        """
        option = self._schema_service.get_option(cog_name, key)
        if option:
            is_valid, error_msg = option.validate_value(value)
            if not is_valid:
                return False, error_msg

        result = await self._session.execute(
            select(GuildConfig).where(
                GuildConfig.guild_id == guild_id,
                GuildConfig.cog_name == cog_name,
                GuildConfig.key == key,
            )
        )
        config = result.scalar_one_or_none()

        if config:
            config.value = value
        else:
            config = GuildConfig(guild_id=guild_id, cog_name=cog_name, key=key, value=value)
            self._session.add(config)

        await self._session.flush()
        logger.debug(f"Configuration updated: {cog_name}.{key} = {value}")
        return True, None

    async def get_all_config(self, guild_id: int, cog_name: str) -> dict[str, Any]:
        """Get all configuration for a cog in a guild.

        Combines stored values with default values from the schema.

        Args:
            guild_id (int): Guild ID
            cog_name (str): Cog name

        Returns:
            dict[str, Any]: Complete configuration dictionary
        """
        schema = self._schema_service.get_schema(cog_name)
        config: dict[str, Any] = {}

        if schema:
            config = schema.get_default_values()

        result = await self._session.execute(
            select(GuildConfig.key, GuildConfig.value).where(
                GuildConfig.guild_id == guild_id, GuildConfig.cog_name == cog_name
            )
        )

        for row in result:
            # Skip null values to preserve defaults
            if row.value is not None:
                config[row.key] = row.value

        return config

    async def is_cog_enabled(self, guild_id: int, cog_name: str, default: bool = False) -> bool:
        """Check if a cog is enabled in a guild.

        Args:
            guild_id (int): Guild ID
            cog_name (str): Cog name
            default (bool): Default value if no record exists

        Returns:
            bool: True if enabled
        """
        result = await self._session.execute(
            select(GuildCogEnabled.enabled).where(
                GuildCogEnabled.guild_id == guild_id,
                GuildCogEnabled.cog_name == cog_name,
            )
        )
        row = result.scalar_one_or_none()
        return row if row is not None else default

    async def set_cog_enabled(self, guild_id: int, cog_name: str, enabled: bool) -> None:
        """Set whether a cog is enabled in a guild.

        Args:
            guild_id (int): Guild ID
            cog_name (str): Cog name
            enabled (bool): True to enable, False to disable
        """
        result = await self._session.execute(
            select(GuildCogEnabled).where(
                GuildCogEnabled.guild_id == guild_id,
                GuildCogEnabled.cog_name == cog_name,
            )
        )
        cog_enabled = result.scalar_one_or_none()

        if cog_enabled:
            cog_enabled.enabled = enabled
        else:
            cog_enabled = GuildCogEnabled(guild_id=guild_id, cog_name=cog_name, enabled=enabled)
            self._session.add(cog_enabled)

        await self._session.flush()
        status = "enabled" if enabled else "disabled"
        logger.info(f"Cog '{cog_name}' {status} in guild {guild_id}")

    async def get_enabled_cogs(self, guild_id: int) -> dict[str, bool]:
        """Get the enabled state of all cogs for a guild.

        Only returns cogs that have an explicit record in the database.

        Args:
            guild_id (int): Guild ID

        Returns:
            dict[str, bool]: Dictionary of cog_name -> enabled
        """
        result = await self._session.execute(
            select(GuildCogEnabled.cog_name, GuildCogEnabled.enabled).where(
                GuildCogEnabled.guild_id == guild_id
            )
        )
        return {row.cog_name: row.enabled for row in result}
