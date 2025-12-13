"""Tests for logging module."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from discord_bot.common.core.logging import setup_logging
from discord_bot.common.core.settings.logging import LoggingSettings


def test_setup_logging_console() -> None:
    """Test logging setup with console output."""
    settings = LoggingSettings(
        log_level="INFO",
        log_file=None,
    )

    setup_logging(settings)

    # Verify logger is configured
    logger = logging.getLogger()
    assert logger.level == logging.INFO


def test_setup_logging_file() -> None:
    """Test logging setup with file output."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="DEBUG",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify logger is configured
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

        # Test logging
        logger.info("Test message")

        # Verify file was created
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content


def test_setup_logging_with_custom_loggers() -> None:
    """Test logging setup with custom logger levels."""
    settings = LoggingSettings(
        log_level="INFO",
        loggers={"discord": "WARNING", "discord_bot": "DEBUG"},
        log_file=None,
    )

    setup_logging(settings)

    # Verify custom logger levels
    discord_logger = logging.getLogger("discord")
    assert discord_logger.level == logging.WARNING

    bot_logger = logging.getLogger("discord_bot")
    assert bot_logger.level == logging.DEBUG


def test_setup_logging_with_rotate_logs() -> None:
    """Test logging setup with log rotation enabled."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=True,
        )

        setup_logging(settings)

        # Verify logger is configured
        logger = logging.getLogger()
        assert logger.level == logging.INFO

        # Verify handler is TimedRotatingFileHandler
        handlers = logger.handlers
        assert len(handlers) > 0

        # Find the file handler (might have multiple handlers)
        file_handler = None
        for handler in handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None, "Expected TimedRotatingFileHandler to be configured"
        assert file_handler.when == "MIDNIGHT"

        # Test logging works
        logger.info("Test rotation message")

        # Verify file was created
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test rotation message" in content


def test_setup_logging_without_rotate_logs() -> None:
    """Test logging setup without log rotation (regular FileHandler)."""
    with TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify logger is configured
        logger = logging.getLogger()
        handlers = logger.handlers

        # Verify it's NOT a TimedRotatingFileHandler
        rotating_handlers = [h for h in handlers if isinstance(h, TimedRotatingFileHandler)]
        assert len(rotating_handlers) == 0, (
            "Should not use TimedRotatingFileHandler when rotate_logs=False"
        )

        # Verify it's a regular FileHandler
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) > 0, "Should use regular FileHandler when rotate_logs=False"

        # Test logging works
        logger.info("Test non-rotating message")
        assert log_file.exists()


def test_setup_logging_creates_log_directory() -> None:
    """Test logging setup creates parent directories for log file."""
    with TemporaryDirectory() as tmpdir:
        # Create a nested path that doesn't exist yet
        log_file = Path(tmpdir) / "nested" / "dirs" / "test.log"

        settings = LoggingSettings(
            log_level="INFO",
            log_file=str(log_file),
            rotate_logs=False,
        )

        setup_logging(settings)

        # Verify parent directories were created
        assert log_file.parent.exists()
        assert log_file.parent.is_dir()

        # Test logging works
        logger = logging.getLogger()
        logger.info("Test directory creation")

        assert log_file.exists()
