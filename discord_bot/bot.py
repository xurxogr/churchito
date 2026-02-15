"""Clase principal del bot de Discord."""

import asyncio
import logging
import time

import discord
from discord.ext import commands

from discord_bot.common.core import AppSettings
from discord_bot.common.enums.event_type import EventType
from discord_bot.common.services import DatabaseService
from discord_bot.common.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)


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
            "discord_bot.general.cog",
            "discord_bot.verification.cog",
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
