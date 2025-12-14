"""Tests for logging module."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from discord_bot.common.core.logging import setup_logging
from discord_bot.common.core.settings.logging import LoggingSettings


def test_setup_logging_console() -> None:
    """Probar opciones de log con consola."""
    settings = LoggingSettings(
        log_level="INFO",
        log_file=None,
    )

    setup_logging(settings)

    # Verificar que el registrador está configurado
    logger = logging.getLogger()
    assert logger.level == logging.INFO


def test_setup_logging_file() -> None:
    """Probar opciones de log con fichero."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="DEBUG",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verificar que el registrador está configurado
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

        # Probar logeo
        logger.info("Mensaje de test")

        # Verificar que el fichero fue creado y contiene el mensaje
        assert log_file.exists()
        content = log_file.read_text()
        assert "Mensaje de test" in content


def test_setup_logging_with_custom_loggers() -> None:
    """Probar opciones de log con niveles de registro personalizados."""
    settings = LoggingSettings(
        log_level="INFO",
        loggers={"discord": "WARNING", "discord_bot": "DEBUG"},
        log_file=None,
    )

    setup_logging(settings)

    # Verificar que los registradores están configurados
    discord_logger = logging.getLogger("discord")
    assert discord_logger.level == logging.WARNING

    bot_logger = logging.getLogger("discord_bot")
    assert bot_logger.level == logging.DEBUG


def test_setup_logging_with_rotate_logs() -> None:
    """Probar opciones de log con rotación habilitada."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=True,
        )

        setup_logging(settings)

        # Verificar que el registrador está configurado
        logger = logging.getLogger()
        assert logger.level == logging.INFO

        # Verificar que el handler es un TimedRotatingFileHandler
        handlers = logger.handlers
        assert len(handlers) > 0

        # Buscar el TimedRotatingFileHandler
        file_handler = None
        for handler in handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None, "TimedRotatingFileHandler necesita ser configurado"
        assert file_handler.when == "MIDNIGHT"

        # Probar logeo
        logger.info("Mensaje de test para rotación")

        # Verificar que el fichero fue creado y contiene el mensaje
        assert log_file.exists()
        content = log_file.read_text()
        assert "Mensaje de test para rotación" in content


def test_setup_logging_without_rotate_logs() -> None:
    """Probar opciones de log con fichero pero sin rotación habilitada."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verificar que el registrador está configurado
        logger = logging.getLogger()
        handlers = logger.handlers

        # Verificar que no hay TimedRotatingFileHandler
        rotating_handlers = [h for h in handlers if isinstance(h, TimedRotatingFileHandler)]
        assert len(rotating_handlers) == 0, (
            "No usar TimedRotatingFileHandler cuando rotate_logs=False"
        )

        # Verificar que hay FileHandler
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0, "Se deber usar FileHandler cuando rotate_logs=False"

        # Probar logeo
        logger.info("Mensaje de prueba sin rotación")
        assert log_file.exists()


def test_setup_logging_creates_log_directory() -> None:
    """Probar que se crea el directorio automáticamente al configurar salvar a fichero."""
    with TemporaryDirectory() as tmpdir:
        # Crear una ruta de fichero en un subdirectorio que no existe
        log_file = Path(tmpdir) / "nested" / "dirs" / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verificar que el directorio fue creado
        assert log_file.parent.exists()
        assert log_file.parent.is_dir()

        # Probar logeo
        logger = logging.getLogger()
        logger.info("Probar creación de directorio de log")

        assert log_file.exists()
