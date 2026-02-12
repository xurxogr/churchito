"""Servicio para operaciones CRUD de configuración de guilds."""

import logging
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.models.guild_cog_enabled import GuildCogEnabled
from discord_bot.common.models.guild_config import GuildConfig
from discord_bot.common.services.config_schema_service import (
    ConfigSchemaService,
    get_config_schema_service,
)

logger = logging.getLogger(__name__)


class ConfigService:
    """Servicio para operaciones de configuración en base de datos.

    Este servicio maneja las operaciones CRUD para valores de configuración
    almacenados en la base de datos. Utiliza el ConfigSchemaService para
    validación y valores por defecto.
    """

    def __init__(
        self, session: AsyncSession, schema_service: ConfigSchemaService | None = None
    ) -> None:
        """Inicializar el servicio de configuración.

        Args:
            session (AsyncSession): Sesión de base de datos
            schema_service (ConfigSchemaService | None): Servicio de esquemas
                (usa singleton si no se proporciona)
        """
        self._session = session
        self._schema_service = schema_service or get_config_schema_service()

    async def get_value(self, guild_id: int, cog_name: str, key: str) -> Any:
        """Obtener un valor de configuración.

        Si no existe un valor almacenado, devuelve el valor por defecto del esquema.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog
            key (str): Clave de la opción

        Returns:
            Any: Valor de configuración o valor por defecto
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
        """Establecer un valor de configuración.

        Valida el valor contra el esquema antes de guardarlo.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog
            key (str): Clave de la opción
            value (Any): Valor a establecer

        Returns:
            tuple[bool, str | None]: (éxito, mensaje_error)
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
        logger.debug(f"Configuración actualizada: {cog_name}.{key} = {value}")
        return True, None

    async def get_all_config(self, guild_id: int, cog_name: str) -> dict[str, Any]:
        """Obtener toda la configuración de un cog para un guild.

        Combina valores almacenados con valores por defecto del esquema.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog

        Returns:
            dict[str, Any]: Diccionario de configuración completa
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
            config[row.key] = row.value

        return config

    async def reset_config(self, guild_id: int, cog_name: str) -> int:
        """Eliminar toda la configuración de un cog para un guild.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog

        Returns:
            int: Número de opciones eliminadas
        """
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(GuildConfig).where(
                    GuildConfig.guild_id == guild_id, GuildConfig.cog_name == cog_name
                )
            ),
        )
        await self._session.flush()
        logger.info(
            f"Configuración reiniciada para guild {guild_id}, "
            f"cog '{cog_name}': {result.rowcount} opciones eliminadas"
        )
        return int(result.rowcount)

    async def is_cog_enabled(self, guild_id: int, cog_name: str, default: bool = True) -> bool:
        """Verificar si un cog está habilitado en un guild.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog
            default (bool): Valor por defecto si no hay registro

        Returns:
            bool: True si está habilitado
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
        """Establecer si un cog está habilitado en un guild.

        Args:
            guild_id (int): ID del guild
            cog_name (str): Nombre del cog
            enabled (bool): True para habilitar, False para deshabilitar
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
        status = "habilitado" if enabled else "deshabilitado"
        logger.info(f"Cog '{cog_name}' {status} en guild {guild_id}")

    async def get_enabled_cogs(self, guild_id: int) -> dict[str, bool]:
        """Obtener el estado de habilitación de todos los cogs para un guild.

        Solo devuelve cogs que tienen un registro explícito en la base de datos.

        Args:
            guild_id (int): ID del guild

        Returns:
            dict[str, bool]: Diccionario de cog_name -> enabled
        """
        result = await self._session.execute(
            select(GuildCogEnabled.cog_name, GuildCogEnabled.enabled).where(
                GuildCogEnabled.guild_id == guild_id
            )
        )
        return {row.cog_name: row.enabled for row in result}
