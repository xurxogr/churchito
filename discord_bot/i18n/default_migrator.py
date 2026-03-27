"""Default value migrator for language changes."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.models.guild_config import GuildConfig
from discord_bot.common.services.config_schema_service import (
    ConfigSchemaService,
    get_config_schema_service,
)
from discord_bot.i18n import I18nService, get_i18n_service

logger = logging.getLogger(__name__)

# Option types that have translatable string defaults
TRANSLATABLE_TYPES = {
    ConfigOptionType.STRING,
    ConfigOptionType.TEXTAREA,
}


class DefaultMigrator:
    """Migrates config values when language changes.

    When a guild changes its language, this migrator updates config values
    that still have their default values to the new language's defaults.
    """

    def __init__(
        self,
        i18n_service: I18nService | None = None,
        schema_service: ConfigSchemaService | None = None,
    ) -> None:
        """Initialize the migrator.

        Args:
            i18n_service: Optional I18nService instance
            schema_service: Optional ConfigSchemaService instance
        """
        self._i18n = i18n_service or get_i18n_service()
        self._schema = schema_service or get_config_schema_service()

    async def migrate_defaults(
        self,
        session: AsyncSession,
        guild_id: int,
        old_lang: str,
        new_lang: str,
    ) -> int:
        """Migrate default values from one language to another.

        For each config option that has a translatable default:
        - If current value equals the old language's default, update to new language's default
        - If current value is customized, leave it unchanged

        Args:
            session: Database session
            guild_id: Guild ID to migrate
            old_lang: Previous language code
            new_lang: New language code

        Returns:
            int: Number of values migrated
        """
        if old_lang == new_lang:
            return 0

        migrated_count = 0

        # Get all schemas
        schemas = self._schema.get_all_schemas()

        for cog_name, schema in schemas.items():
            for option in schema.options:
                # Only migrate translatable types with defaults
                if option.option_type not in TRANSLATABLE_TYPES:
                    continue
                if option.default is None:
                    continue

                # Get translated defaults for both languages
                old_default = self._get_translated_default(
                    cog_name, option.key, old_lang, option.default
                )
                new_default = self._get_translated_default(
                    cog_name, option.key, new_lang, option.default
                )

                # Skip if defaults are the same
                if old_default == new_default:
                    continue

                # Check if current value matches old default
                current_value = await self._get_current_value(
                    session, guild_id, cog_name, option.key
                )

                # If value is None (not set) or matches old default, update it
                if current_value is None or self._values_match(current_value, old_default):
                    migrated = await self._update_value(
                        session, guild_id, cog_name, option.key, new_default
                    )
                    if migrated:
                        migrated_count += 1
                        logger.debug(
                            f"Migrated {cog_name}.{option.key} from '{old_lang}' to '{new_lang}'"
                        )

        if migrated_count > 0:
            await session.flush()
            logger.info(
                f"Migrated {migrated_count} config values for guild {guild_id} "
                f"from '{old_lang}' to '{new_lang}'"
            )

        return migrated_count

    def _get_translated_default(
        self,
        cog_name: str,
        option_key: str,
        lang: str,
        original_default: Any,
    ) -> Any:
        """Get the translated default value for an option.

        Args:
            cog_name: Name of the cog
            option_key: Config option key
            lang: Language code
            original_default: Original default value

        Returns:
            Translated default value or original if not found
        """
        return self._i18n.get_translated_default(
            cog_name=cog_name,
            key=option_key,
            lang=lang,
            fallback=original_default,
        )

    async def _get_current_value(
        self,
        session: AsyncSession,
        guild_id: int,
        cog_name: str,
        key: str,
    ) -> Any | None:
        """Get the current value from the database.

        Args:
            session: Database session
            guild_id: Guild ID
            cog_name: Cog name
            key: Config key

        Returns:
            Current value or None if not set
        """
        result = await session.execute(
            select(GuildConfig.value).where(
                GuildConfig.guild_id == guild_id,
                GuildConfig.cog_name == cog_name,
                GuildConfig.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def _update_value(
        self,
        session: AsyncSession,
        guild_id: int,
        cog_name: str,
        key: str,
        new_value: Any,
    ) -> bool:
        """Update a config value in the database.

        Args:
            session: Database session
            guild_id: Guild ID
            cog_name: Cog name
            key: Config key
            new_value: New value to set

        Returns:
            bool: True if value was updated
        """
        result = await session.execute(
            select(GuildConfig).where(
                GuildConfig.guild_id == guild_id,
                GuildConfig.cog_name == cog_name,
                GuildConfig.key == key,
            )
        )
        config = result.scalar_one_or_none()

        if config:
            config.value = new_value
        else:
            config = GuildConfig(
                guild_id=guild_id,
                cog_name=cog_name,
                key=key,
                value=new_value,
            )
            session.add(config)

        return True

    def _values_match(self, value1: Any, value2: Any) -> bool:
        """Check if two values match for migration purposes.

        Args:
            value1: First value
            value2: Second value

        Returns:
            bool: True if values are considered matching
        """
        # Normalize strings for comparison
        if isinstance(value1, str) and isinstance(value2, str):
            return value1.strip() == value2.strip()
        return bool(value1 == value2)


def get_default_migrator() -> DefaultMigrator:
    """Get a DefaultMigrator instance.

    Returns:
        DefaultMigrator: A default migrator instance
    """
    return DefaultMigrator()
