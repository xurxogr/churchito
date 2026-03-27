"""Main entry point for the Discord bot."""

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
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Discord bot with cog-based architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (default: ~/.config/discord-bot/config.json)",
    )

    parser.add_argument(
        "--token",
        type=str,
        help="Discord bot token (overrides configuration file)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (overrides configuration file)",
    )

    return parser.parse_args()


def load_settings(args: argparse.Namespace) -> AppSettings:
    """Load application settings.

    Args:
        args (argparse.Namespace): Parsed command line arguments

    Returns:
        AppSettings: Application settings
    """
    # Override config file path if provided
    if args.config:
        AppSettings.model_config["json_file"] = str(args.config)

    settings = get_settings()

    # Override with command line arguments
    if args.token:
        settings.bot.token = args.token

    if args.log_level:
        settings.logging.log_level = args.log_level

    return settings


async def run_bot(bot: DiscordBot, token: str) -> None:
    """Run the Discord bot.

    Args:
        bot (DiscordBot): Bot instance
        token (str): Authentication token
    """
    async with bot:
        await bot.start(token)


async def run_web(settings: AppSettings, database: DatabaseService, bot: DiscordBot) -> None:
    """Run the web dashboard server.

    Args:
        settings (AppSettings): Application settings
        database (DatabaseService): Database service
        bot (DiscordBot): Bot instance (for accessing guilds, etc.)
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
    """Main entry point for the bot."""
    # Parse arguments
    args = parse_args()

    # Load settings
    try:
        settings = load_settings(args)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        print(
            "\nPlease create a configuration file at ~/.config/discord-bot/config.json",
            file=sys.stderr,
        )
        print("or use --config to specify a different location.", file=sys.stderr)
        print("\nConfiguration example:", file=sys.stderr)
        print('{\n  "bot": {"token": "YOUR_BOT_TOKEN"}\n}', file=sys.stderr)
        sys.exit(1)

    # Set up logging
    setup_logging(settings.logging)
    logger.info("Starting Discord bot...")

    # Validate bot token
    if not settings.bot.token:
        logger.error("Bot token not configured")
        logger.error("Set the BOT__TOKEN environment variable or add it to the configuration file")
        sys.exit(1)

    # Initialize database service
    database = DatabaseService(settings.database)

    # Create the bot
    bot = DiscordBot(settings, database)

    try:
        if settings.web.enabled:
            # Run bot and web dashboard in parallel
            logger.info(f"Web dashboard enabled at http://{settings.web.host}:{settings.web.port}")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(run_bot(bot, settings.bot.token))
                tg.create_task(run_web(settings, database, bot))
        else:
            # Run bot only
            await run_bot(bot, settings.bot.token)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


def run() -> None:
    """Run the bot (synchronous wrapper)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
