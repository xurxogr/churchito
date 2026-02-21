"""Clase principal del bot de Discord."""

import asyncio
import logging
import time

import discord
from discord.ext import commands
from sqlalchemy import select

from discord_bot.common.core import AppSettings
from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.enums.event_type import EventType
from discord_bot.common.models import Guild as GuildModel
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services import DatabaseService
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

# Esquema de configuración del bot (permisos de administración)
BOT_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="bot",
    display_name="Bot",
    description="Configuración general del bot y permisos de administración",
    icon="🤖",
    toggleable=False,
    options=[
        ConfigOption(
            key="admin_roles",
            name="Roles de administración",
            description=(
                "Roles que pueden configurar el bot desde el panel web. "
                "El usuario que invitó al bot y el owner del servidor siempre tienen acceso."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
        ),
    ],
)


class DiscordBot(commands.Bot):
    """Clase principal del bot de Discord."""

    def __init__(self, settings: AppSettings, database: DatabaseService) -> None:
        """Inicializa el bot de Discord.

        Args:
            settings (AppSettings): Configuración de la aplicación
            database (DatabaseService): Servicio de base de datos
        """
        self.settings = settings
        self.database = database
        self.event_bus = get_event_bus()
        self._monitor_task: asyncio.Task[None] | None = None

        # Configurar intents
        # Nota: message_content y members son intents privilegiados que deben
        # habilitarse en el Portal de Desarrolladores de Discord
        intents = discord.Intents.default()
        intents.message_content = True  # Requerido para leer contenido de mensajes
        intents.members = True  # Requerido para información de miembros

        # Inicializar bot
        super().__init__(
            command_prefix=settings.bot.command_prefix,
            description=settings.bot.description,
            intents=intents,
            owner_id=settings.bot.owner_id,
        )

    async def setup_hook(self) -> None:
        """Inicialización del hook.

        Hook llamado durante la inicialización del bot para cargar extensiones y configurar
        la base de datos.
        """
        logger.info("Ejecutando el hook de configuración...")

        # Registrar esquema de configuración del bot
        get_config_schema_service().register_schema(BOT_CONFIG_SCHEMA)

        # Inicializar base de datos
        await self.database.initialize()

        # Crear tablas
        await self._create_tables()

        # Cargar cogs
        await self._load_cogs()

        # Iniciar monitoreo del bucle de eventos
        self._monitor_task = asyncio.create_task(self._monitor_event_loop())

        logger.info("Hook de configuración completado")

    async def _create_tables(self) -> None:
        """Aplica migraciones de Alembic a la base de datos."""
        from alembic import command
        from alembic.config import Config

        # Configurar Alembic
        alembic_cfg = Config("alembic.ini")

        # Ejecutar migraciones en un thread para no bloquear el event loop
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")

        logger.info("Migraciones de base de datos aplicadas")

    async def _load_cogs(self) -> None:
        """Carga todos los cogs."""
        cogs_to_load = [
            "discord_bot.verification.cog",
            "discord_bot.autoname.cog",
            "discord_bot.purga.cog",
        ]

        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logger.info(f"Cargado cog: {cog}")
            except Exception as e:
                logger.error(f"Error al cargar el cog {cog}: {e}", exc_info=True)

    async def on_ready(self) -> None:
        """Manejador de evento cuando el bot está listo."""
        if self.user:
            logger.info(f"Bot conectado como {self.user.name} (ID: {self.user.id})")
            logger.info(f"Conectado a {len(self.guilds)} servidor(s)")
            for guild in self.guilds:
                logger.info(f"  - {guild.name} (ID: {guild.id})")

            # Sincronizar comandos de aplicación con Discord
            try:
                synced = await self.tree.sync()
                logger.info(f"Sincronizados {len(synced)} comandos de aplicación")
            except Exception as e:
                logger.error(f"Error al sincronizar comandos: {e}")

            # Emitir evento
            self.event_bus.emit(
                EventType.BOT_READY,
                {
                    "bot_name": self.user.name,
                    "bot_id": self.user.id,
                    "guild_count": len(self.guilds),
                },
            )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Manejador de evento cuando el bot se une a un servidor.

        Registra el servidor en la base de datos y guarda quién invitó al bot.
        """
        logger.info(f"Bot unido al servidor: {guild.name} (ID: {guild.id})")

        # Intentar obtener quién invitó al bot desde el audit log
        invited_by_id: int | None = None
        try:
            if guild.me and guild.me.guild_permissions.view_audit_log and self.user:
                async for entry in guild.audit_logs(
                    limit=10, action=discord.AuditLogAction.bot_add
                ):
                    # Buscar la entrada que corresponde a este bot
                    if entry.target and entry.user and entry.target.id == self.user.id:
                        invited_by_id = entry.user.id
                        logger.info(f"Bot invitado por: {entry.user.name} (ID: {invited_by_id})")
                        break
        except discord.Forbidden:
            logger.warning(
                f"No se pudo acceder al audit log de {guild.name} para determinar "
                "quién invitó al bot"
            )
        except Exception as e:
            logger.error(f"Error al consultar audit log: {e}")

        # Si no pudimos obtener el invitador, usar el owner del servidor
        if invited_by_id is None:
            invited_by_id = guild.owner_id
            logger.info(f"Usando owner del servidor como invitador: {invited_by_id}")

        # Guardar en la base de datos
        await self._save_guild(guild, invited_by_id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Manejador de evento cuando el bot es removido de un servidor."""
        logger.info(f"Bot removido del servidor: {guild.name} (ID: {guild.id})")
        logger.info(f"Ahora conectado a {len(self.guilds)} servidor(s)")

    async def _save_guild(self, guild: discord.Guild, invited_by_id: int | None) -> None:
        """Guardar o actualizar un servidor en la base de datos.

        Args:
            guild (discord.Guild): El servidor de Discord
            invited_by_id (int | None): ID del usuario que invitó al bot
        """
        async with self.database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == guild.id))
            db_guild = result.scalar_one_or_none()

            if db_guild:
                db_guild.name = guild.name
                # Solo actualizar invited_by_id si no estaba establecido
                if db_guild.invited_by_id is None and invited_by_id:
                    db_guild.invited_by_id = invited_by_id
            else:
                db_guild = GuildModel(
                    id=guild.id,
                    name=guild.name,
                    invited_by_id=invited_by_id,
                )
                session.add(db_guild)

            await session.commit()
            logger.info(f"Servidor guardado en BD: {guild.name}")

    async def _monitor_event_loop(self) -> None:
        """Monitorea el bucle de eventos en busca de operaciones bloqueantes.

        Esta tarea se ejecuta continuamente y comprueba retrasos en el bucle de eventos
        que puedan indicar operaciones bloqueantes. Registra advertencias cuando
        se detecta un retraso significativo.
        """
        logger.info("Monitoreo del bucle de eventos iniciado")
        last_check = time.perf_counter()
        check_interval = 0.1  # Comprobar cada 100ms
        warning_threshold = self.settings.bot.event_loop_warning_threshold

        try:
            while True:
                await asyncio.sleep(check_interval)
                now = time.perf_counter()
                actual_delay = now - last_check
                expected_delay = check_interval
                lag = actual_delay - expected_delay

                if lag > warning_threshold:
                    logger.warning(
                        f"Retraso en el bucle de eventos detectado: {lag:.2f}s "
                        f"(esperado {expected_delay:.2f}s, actual {actual_delay:.2f}s). "
                        "¡Esto puede indicar una operación bloqueante en un cog!"
                    )

                last_check = now
        except asyncio.CancelledError:
            logger.info("Monitoreo del bucle de eventos detenido")
            raise

    async def close(self) -> None:
        """Apagado limpio del bot."""
        logger.info("Apagando el bot...")

        # Detener monitoreo del bucle de eventos
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Emitir evento de apagado
        self.event_bus.emit(EventType.BOT_SHUTDOWN, {})

        # Cerrar base de datos
        await self.database.close()

        # Cerrar conexión del bot
        await super().close()

        logger.info("Apagado del bot completado")
