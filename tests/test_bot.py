"""Tests de la clase principal."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.core import AppSettings
from discord_bot.common.services import DatabaseService


@pytest.fixture
async def test_bot(
    test_settings: AppSettings, test_database: DatabaseService
) -> AsyncGenerator[DiscordBot, None]:
    """Fixture para crear una instancia de bot de prueba.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba

    Returns:
        DiscordBot: Instancia del bot de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        # Falsear propiedades necesarias
        type(bot).guilds = PropertyMock(return_value=[])  # type: ignore[method-assign]
        mock_user = MagicMock()
        mock_user.name = "TestBot"
        mock_user.id = 123456789
        type(bot).user = PropertyMock(return_value=mock_user)  # type: ignore[method-assign]
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        yield bot


def test_bot_initialization(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Probar inicialización del bot.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        assert bot.settings == test_settings
        assert bot.database == test_database
        assert bot.event_bus is not None


async def test_bot_on_ready(test_bot: DiscordBot) -> None:
    """Probar el método on_ready del bot.

    Args:
        test_bot: Instancia del bot de prueba
    """
    # Falsear el método emit del event bus
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Llamar on_ready
    await test_bot.on_ready()

    # Verificar que se emitió el evento correcto
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 0,
        },
    )


async def test_bot_close(test_bot: DiscordBot) -> None:
    """Probar el método close del bot.

    Args:
        test_bot: Instancia del bot de prueba
    """
    # Falsear el cierre de la base de datos
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Falsear el método emit del event bus
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Crear una tarea de monitor falsa
    async def dummy_monitor() -> None:
        await asyncio.sleep(100)  # Long sleep to simulate running task

    monitor_task = asyncio.create_task(dummy_monitor())
    test_bot._monitor_task = monitor_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verificar que se emitió el evento de apagado
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verificar que la tarea de monitor fue cancelada
        assert monitor_task.cancelled()

        # Verificar que la base de datos fue cerrada
        test_bot.database.close.assert_called_once()


async def test_bot_setup_hook(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Probar el método setup_hook del bot.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]

        # Falsear la inicialización de la base de datos
        test_database.initialize = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock) as mock_create_tables,
            patch.object(bot, "_load_cogs", new_callable=AsyncMock) as mock_load_cogs,
        ):
            await bot.setup_hook()

            # Verificar que se llamaron los métodos correctos
            test_database.initialize.assert_called_once()
            mock_create_tables.assert_called_once()
            mock_load_cogs.assert_called_once()


async def test_bot_load_cogs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar la carga exitosa de cogs del bot.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]

        # Debería cargar sin errores
        await bot._load_cogs()

        # Validar que se llamaron las extensiones esperadas
        assert bot.load_extension.call_count > 0
        bot.load_extension.assert_any_call("discord_bot.general.cog")


async def test_bot_load_cogs_with_error(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar la carga de cogs del bot con errores.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock(side_effect=Exception("Test error"))  # type: ignore[method-assign]

        # Debería manejar el error internamente
        await bot._load_cogs()

        # Validar que se llamaron las extensiones esperadas
        assert bot.load_extension.call_count > 0


async def test_bot_create_tables(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar la creación de tablas de la base de datos del bot.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Falsear el engine y la conexión
        mock_conn = AsyncMock()
        mock_begin_context = AsyncMock()
        mock_begin_context.__aenter__.return_value = mock_conn
        mock_begin_context.__aexit__.return_value = None

        # Falsear el engine para devolver el contexto de begin
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_begin_context

        # Parchear el engine del bot para usar el mock
        with patch.object(
            type(test_database), "engine", new_callable=PropertyMock
        ) as mock_engine_prop:
            mock_engine_prop.return_value = mock_engine

            await bot._create_tables()

            # Verificar que se llamó a run_sync para crear tablas
            mock_conn.run_sync.assert_called_once()


async def test_bot_close_with_done_monitor_task(test_bot: DiscordBot) -> None:
    """Probar el cierre del bot cuando la tarea de monitor ya está completada.

    Args:
        test_bot: Instancia del bot de prueba
    """
    # Falsear el cierre de la base de datos
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Falsear el método emit del event bus
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Falsear una tarea de monitor ya completada
    mock_task = AsyncMock()
    mock_task.done.return_value = True
    test_bot._monitor_task = mock_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verificar que se emitió el evento de apagado
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verificar que la tarea de monitor no fue cancelada (ya estaba done)
        test_bot.database.close.assert_called_once()


async def test_bot_close_without_monitor_task(test_bot: DiscordBot) -> None:
    """Probar el cierre del bot cuando no hay tarea de monitor.

    Args:
        test_bot: Instancia del bot de prueba
    """
    # Falsear el cierre de la base de datos
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Falsear el método emit del event bus
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Sin tarea de monitor
    test_bot._monitor_task = None

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verificar que se emitió el evento de apagado
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verificar que la base de datos fue cerrada
        test_bot.database.close.assert_called_once()


async def test_monitor_event_loop_cancellation(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar la cancelación del monitor del bucle de eventos.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Empezar el monitor
        task = asyncio.create_task(bot._monitor_event_loop())

        # Dejarlo correr un poco
        await asyncio.sleep(0.2)

        # Cancelar la tarea
        task.cancel()

        # Verificar que se cancela sin errores
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_monitor_event_loop_detects_lag(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que el monitor del bucle de eventos detecta retrasos.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    import time

    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Establecer un umbral bajo para la prueba
        bot.settings.bot.event_loop_warning_threshold = 0.1

        # Falsear el logger
        with patch("discord_bot.bot.logger") as mock_logger:
            # Empezar el monitor
            task = asyncio.create_task(bot._monitor_event_loop())

            # Dejarlo correr un poco
            await asyncio.sleep(0.15)

            # Introducir un retraso artificial
            time.sleep(0.6)  # noqa: ASYNC251

            # Dar tiempo al monitor para detectar el retraso
            await asyncio.sleep(0.15)

            # Cancelar la tarea
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verificar que se registró una advertencia sobre el retraso
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Retraso en el bucle de eventos detectado" in str(call)
            ]
            assert len(warning_calls) > 0, "Expected warning about event loop delay"


async def test_monitor_event_loop_uses_custom_threshold(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que el monitor del bucle de eventos usa un umbral personalizado.

    Args:
        test_settings (AppSettings): Configuración de la aplicación de prueba
        test_database (DatabaseService): Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        # Establecer un umbral alto para la prueba
        test_settings.bot.event_loop_warning_threshold = 2.0
        bot = DiscordBot(test_settings, test_database)

        # Falsear el logger
        with patch("discord_bot.bot.logger") as mock_logger:
            # Empezar el monitor
            task = asyncio.create_task(bot._monitor_event_loop())

            # Dejarlo correr un poco
            await asyncio.sleep(0.2)

            # Cancelar la tarea
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Confirmar que no se registraron advertencias
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Retraso en el bucle de eventos detectado" in str(call)
            ]
            assert len(warning_calls) == 0, "Should not log warnings with high threshold"


async def test_bot_on_ready_without_user(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar on_ready cuando el usuario del bot es None.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        type(bot).user = PropertyMock(return_value=None)  # type: ignore[method-assign]

        mock_emit = MagicMock()
        bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

        # Debería ejecutar sin errores cuando user es None
        await bot.on_ready()

        # No debería emitir evento cuando no hay usuario
        mock_emit.assert_not_called()


async def test_bot_on_ready_sync_error(test_bot: DiscordBot) -> None:
    """Probar on_ready cuando tree.sync() lanza una excepción.

    Args:
        test_bot: Instancia del bot de prueba
    """
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Falsear tree.sync para que lance una excepción
    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(side_effect=Exception("Sync failed"))
    type(test_bot).tree = PropertyMock(return_value=mock_tree)  # type: ignore[method-assign]

    # Debería manejar el error sin propagarlo
    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verificar que se registró el error
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if "Error al sincronizar comandos" in str(call)
        ]
        assert len(error_calls) > 0, "Expected error log about sync failure"

    # El evento debería haberse emitido igualmente
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 0,
        },
    )


async def test_bot_on_ready_sync_success(test_bot: DiscordBot) -> None:
    """Probar on_ready cuando tree.sync() tiene éxito.

    Args:
        test_bot: Instancia del bot de prueba
    """
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Falsear tree.sync para que devuelva comandos sincronizados
    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
    type(test_bot).tree = PropertyMock(return_value=mock_tree)  # type: ignore[method-assign]

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verificar que se registró la sincronización exitosa
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Sincronizados 2 comandos" in str(call)
        ]
        assert len(info_calls) > 0, "Expected info log about synced commands"


async def test_bot_setup_hook_creates_monitor_task(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que setup_hook crea la tarea de monitoreo.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        test_database.initialize = AsyncMock()  # type: ignore[method-assign]

        # Falsear _create_tables y _load_cogs
        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock),
            patch.object(bot, "_load_cogs", new_callable=AsyncMock),
        ):
            await bot.setup_hook()

            # Verificar que se creó la tarea de monitoreo
            assert bot._monitor_task is not None
            assert not bot._monitor_task.done()

            # Limpiar la tarea
            bot._monitor_task.cancel()
            try:
                await bot._monitor_task
            except asyncio.CancelledError:
                pass


def test_bot_initialization_sets_intents(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que la inicialización configura los intents correctamente.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__") as mock_init:
        mock_init.return_value = None

        DiscordBot(test_settings, test_database)

        # Verificar que se llamó al constructor padre con los argumentos correctos
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs

        assert call_kwargs["command_prefix"] == test_settings.bot.command_prefix
        assert call_kwargs["description"] == test_settings.bot.description
        assert call_kwargs["owner_id"] == test_settings.bot.owner_id

        # Verificar intents
        intents = call_kwargs["intents"]
        assert intents.message_content is True
        assert intents.members is True


def test_bot_initialization_with_different_settings(
    test_database: DatabaseService,
) -> None:
    """Probar inicialización con diferentes configuraciones.

    Args:
        test_database: Servicio de base de datos de prueba
    """
    from discord_bot.common.core import AppSettings
    from discord_bot.common.core.settings.bot import BotSettings

    custom_settings = AppSettings(
        bot=BotSettings(
            token="test_token",
            command_prefix=">>",
            description="Custom Bot Description",
            owner_id=999888777,
        )
    )

    with patch("discord_bot.bot.commands.Bot.__init__") as mock_init:
        mock_init.return_value = None

        bot = DiscordBot(custom_settings, test_database)

        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["command_prefix"] == ">>"
        assert call_kwargs["description"] == "Custom Bot Description"
        assert call_kwargs["owner_id"] == 999888777
        assert bot.settings == custom_settings


async def test_bot_on_ready_logs_guild_count(test_bot: DiscordBot) -> None:
    """Probar que on_ready registra el conteo de guilds.

    Args:
        test_bot: Instancia del bot de prueba
    """
    # Configurar múltiples guilds
    mock_guilds = [MagicMock(), MagicMock(), MagicMock()]
    type(test_bot).guilds = PropertyMock(return_value=mock_guilds)  # type: ignore[method-assign]

    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[])
    type(test_bot).tree = PropertyMock(return_value=mock_tree)  # type: ignore[method-assign]

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verificar que se registró el conteo de guilds
        info_calls = [
            call for call in mock_logger.info.call_args_list if "3 servidor(s)" in str(call)
        ]
        assert len(info_calls) > 0, "Expected info log about guild count"

    # Verificar el evento emitido
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 3,
        },
    )


async def test_bot_load_cogs_loads_all_configured_cogs(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que _load_cogs intenta cargar todos los cogs configurados.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]

        with patch("discord_bot.bot.logger") as mock_logger:
            await bot._load_cogs()

            # Verificar que se registró la carga exitosa
            info_calls = [
                call for call in mock_logger.info.call_args_list if "Cargado cog:" in str(call)
            ]
            assert len(info_calls) > 0, "Expected info log about loaded cogs"


async def test_bot_load_cogs_logs_errors(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que _load_cogs registra errores al cargar cogs.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("Failed to load")
        )

        with patch("discord_bot.bot.logger") as mock_logger:
            await bot._load_cogs()

            # Verificar que se registró el error
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "Error al cargar el cog" in str(call)
            ]
            assert len(error_calls) > 0, "Expected error log about cog loading failure"


async def test_bot_create_tables_logs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que _create_tables registra la creación exitosa.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        mock_conn = AsyncMock()
        mock_begin_context = AsyncMock()
        mock_begin_context.__aenter__.return_value = mock_conn
        mock_begin_context.__aexit__.return_value = None

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_begin_context

        with (
            patch.object(
                type(test_database), "engine", new_callable=PropertyMock
            ) as mock_engine_prop,
            patch("discord_bot.bot.logger") as mock_logger,
        ):
            mock_engine_prop.return_value = mock_engine

            await bot._create_tables()

            # Verificar que se registró la creación de tablas
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Tablas de la base de datos creadas" in str(call)
            ]
            assert len(info_calls) > 0, "Expected info log about tables creation"


async def test_bot_close_logs_shutdown(test_bot: DiscordBot) -> None:
    """Probar que close registra el proceso de apagado.

    Args:
        test_bot: Instancia del bot de prueba
    """
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]
    test_bot.event_bus.emit = MagicMock()  # type: ignore[method-assign]
    test_bot._monitor_task = None

    with (
        patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock),
        patch("discord_bot.bot.logger") as mock_logger,
    ):
        await test_bot.close()

        # Verificar mensajes de log
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Apagando el bot" in call for call in info_calls)
        assert any("Apagado del bot completado" in call for call in info_calls)


async def test_bot_setup_hook_logs_progress(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que setup_hook registra el progreso.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        test_database.initialize = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock),
            patch.object(bot, "_load_cogs", new_callable=AsyncMock),
            patch("discord_bot.bot.logger") as mock_logger,
        ):
            await bot.setup_hook()

            # Verificar mensajes de log
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Ejecutando el hook de configuración" in call for call in info_calls)
            assert any("Hook de configuración completado" in call for call in info_calls)

            # Limpiar
            if bot._monitor_task:
                bot._monitor_task.cancel()
                try:
                    await bot._monitor_task
                except asyncio.CancelledError:
                    pass


async def test_monitor_event_loop_logs_start(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que _monitor_event_loop registra el inicio.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        with patch("discord_bot.bot.logger") as mock_logger:
            task = asyncio.create_task(bot._monitor_event_loop())
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verificar que se registró el inicio
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Monitoreo del bucle de eventos iniciado" in str(call)
            ]
            assert len(info_calls) > 0


async def test_monitor_event_loop_logs_stop(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Probar que _monitor_event_loop registra la detención.

    Args:
        test_settings: Configuración de la aplicación de prueba
        test_database: Servicio de base de datos de prueba
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        with patch("discord_bot.bot.logger") as mock_logger:
            task = asyncio.create_task(bot._monitor_event_loop())
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verificar que se registró la detención
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Monitoreo del bucle de eventos detenido" in str(call)
            ]
            assert len(info_calls) > 0
