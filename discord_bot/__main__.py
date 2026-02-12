"""Punto de entrada principal para el bot de Discord."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from discord_bot.bot import DiscordBot
from discord_bot.common.core import AppSettings, get_settings
from discord_bot.common.core.logging import setup_logging
from discord_bot.common.services import DatabaseService
from discord_bot.web.app import create_app

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Procesa los argumentos de línea de comandos.

    Returns:
        argparse.Namespace: Argumentos procesados
    """
    parser = argparse.ArgumentParser(
        description="Bot de Discord con arquitectura basada en cogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Ruta al archivo de configuración (por defecto: ~/.config/discord-bot/config.json)",
    )

    parser.add_argument(
        "--token",
        type=str,
        help="Token del bot de Discord (anula el archivo de configuración)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Nivel de registro (anula el archivo de configuración)",
    )

    return parser.parse_args()


def load_settings(args: argparse.Namespace) -> AppSettings:
    """Carga la configuración de la aplicación.

    Args:
        args (argparse.Namespace): Argumentos de línea de comandos procesados

    Returns:
        AppSettings: Configuración de la aplicación
    """
    # Anula la ruta del archivo de configuración si se proporciona
    if args.config:
        AppSettings.model_config["json_file"] = str(args.config)

    settings = get_settings()

    # Anula con argumentos de línea de comandos
    if args.token:
        settings.bot.token = args.token

    if args.log_level:
        settings.logging.log_level = args.log_level

    return settings


async def run_bot(bot: DiscordBot, token: str) -> None:
    """Ejecuta el bot de Discord.

    Args:
        bot (DiscordBot): Instancia del bot
        token (str): Token de autenticación
    """
    async with bot:
        await bot.start(token)


async def run_web(settings: AppSettings, database: DatabaseService, bot: DiscordBot) -> None:
    """Ejecuta el servidor web del dashboard.

    Args:
        settings (AppSettings): Configuración de la aplicación
        database (DatabaseService): Servicio de base de datos
        bot (DiscordBot): Instancia del bot (para acceder a guilds, etc.)
    """
    app = create_app(settings, database, bot)

    config = uvicorn.Config(
        app,
        host=settings.web.host,
        port=settings.web.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    """Punto de entrada principal del bot."""
    # Procesa argumentos
    args = parse_args()

    # Carga configuración
    try:
        settings = load_settings(args)
    except Exception as e:
        print(f"Error al cargar la configuración: {e}", file=sys.stderr)
        print(
            "\nPor favor, crea un archivo de configuración en ~/.config/discord-bot/config.json",
            file=sys.stderr,
        )
        print("o usa --config para especificar una ubicación diferente.", file=sys.stderr)
        print("\nEjemplo de configuración:", file=sys.stderr)
        print('{\n  "bot": {"token": "TU_TOKEN_DEL_BOT"}\n}', file=sys.stderr)
        sys.exit(1)

    # Configura el registro de eventos
    setup_logging(settings.logging)
    logger.info("Iniciando el bot de Discord...")

    # Valida el token del bot
    if not settings.bot.token:
        logger.error("Token del bot no configurado")
        logger.error(
            "Establece la variable de entorno BOT__TOKEN o añádelo al archivo de configuración"
        )
        sys.exit(1)

    # Inicializa el servicio de base de datos
    database = DatabaseService(settings.database)

    # Crea el bot
    bot = DiscordBot(settings, database)

    try:
        if settings.web.enabled:
            # Ejecutar bot y web dashboard en paralelo
            logger.info(
                f"Dashboard web habilitado en http://{settings.web.host}:{settings.web.port}"
            )
            async with asyncio.TaskGroup() as tg:
                tg.create_task(run_bot(bot, settings.bot.token))
                tg.create_task(run_web(settings, database, bot))
        else:
            # Solo ejecutar el bot
            await run_bot(bot, settings.bot.token)
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida, apagando...")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        sys.exit(1)


def run() -> None:
    """Ejecuta el bot (wrapper síncrono)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
