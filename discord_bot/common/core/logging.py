"""Configuración de registro para Discord Bot."""

import logging
import sys
from collections.abc import Sequence
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from discord_bot.common.core.settings.logging import LoggingSettings


def setup_logging(settings: LoggingSettings) -> None:
    """Configura la logging para la aplicación.

    Args:
        settings (LoggingSettings): Configuración para el sistema de logs.
    """
    handlers: Sequence[logging.Handler]
    if settings.log_file:
        log_path = Path(settings.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if settings.rotate_logs:
            handlers = [
                TimedRotatingFileHandler(
                    filename=log_path,
                    when="midnight",
                    encoding="utf-8",
                )
            ]
        else:
            handlers = [logging.FileHandler(log_path)]
    else:
        handlers = [logging.StreamHandler(sys.stdout)]

    handlers[0].setFormatter(
        logging.Formatter(fmt=settings.log_format, datefmt=settings.date_format)
    )
    logging.basicConfig(
        level=settings.log_level,
        format=settings.log_format,
        handlers=handlers,
        force=True,
    )

    # Configura los niveles de los loggers individuales
    for logger_name, level in settings.loggers.items():
        logging.getLogger(logger_name).setLevel(level)
