"""Tests for logging module."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from discord_bot.common.core.logging import setup_logging
from discord_bot.common.core.settings.logging import LoggingSettings


def test_setup_logging_console() -> None:
    """Test log options with console."""
    settings = LoggingSettings(
        log_level="INFO",
        log_file=None,
    )

    setup_logging(settings)

    # Verify that the logger is configured
    logger = logging.getLogger()
    assert logger.level == logging.INFO


def test_setup_logging_file() -> None:
    """Test log options with file."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="DEBUG",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify that the logger is configured
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

        # Test logging
        logger.info("Test message")

        # Verify that the file was created and contains the message
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content


def test_setup_logging_with_custom_loggers() -> None:
    """Test log options with custom log levels."""
    settings = LoggingSettings(
        log_level="INFO",
        loggers={"discord": "WARNING", "discord_bot": "DEBUG"},
        log_file=None,
    )

    setup_logging(settings)

    # Verify that the loggers are configured
    discord_logger = logging.getLogger("discord")
    assert discord_logger.level == logging.WARNING

    bot_logger = logging.getLogger("discord_bot")
    assert bot_logger.level == logging.DEBUG


def test_setup_logging_with_rotate_logs() -> None:
    """Test log options with rotation enabled."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=True,
        )

        setup_logging(settings)

        # Verify that the logger is configured
        logger = logging.getLogger()
        assert logger.level == logging.INFO

        # Verify that the handler is a TimedRotatingFileHandler
        handlers = logger.handlers
        assert len(handlers) > 0

        # Find the TimedRotatingFileHandler
        file_handler = None
        for handler in handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None, "TimedRotatingFileHandler needs to be configured"
        assert file_handler.when == "MIDNIGHT"

        # Test logging
        logger.info("Test message for rotation")

        # Verify that the file was created and contains the message
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message for rotation" in content


def test_setup_logging_without_rotate_logs() -> None:
    """Test log options with file but without rotation enabled."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify that the logger is configured
        logger = logging.getLogger()
        handlers = logger.handlers

        # Verify that there is no TimedRotatingFileHandler
        rotating_handlers = [h for h in handlers if isinstance(h, TimedRotatingFileHandler)]
        assert len(rotating_handlers) == 0, (
            "Should not use TimedRotatingFileHandler when rotate_logs=False"
        )

        # Verify that there is a FileHandler
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0, "Should use FileHandler when rotate_logs=False"

        # Test logging
        logger.info("Test message without rotation")
        assert log_file.exists()


def test_setup_logging_creates_log_directory() -> None:
    """Test that the directory is created automatically when configuring file output."""
    with TemporaryDirectory() as tmpdir:
        # Create a file path in a subdirectory that doesn't exist
        log_file = Path(tmpdir) / "nested" / "dirs" / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify that the directory was created
        assert log_file.parent.exists()
        assert log_file.parent.is_dir()

        # Test logging
        logger = logging.getLogger()
        logger.info("Test log directory creation")

        assert log_file.exists()
