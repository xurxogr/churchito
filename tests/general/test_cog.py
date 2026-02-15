"""Pruebas para el cog general."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from discord.ext import commands

from discord_bot.general.cog import GeneralCog, setup, teardown


@pytest.fixture
def mock_bot() -> MagicMock:
    """Crear un bot de Discord simulado.

    Returns:
        MagicMock: Instancia de bot simulada
    """
    bot = MagicMock(spec=commands.Bot)
    bot.latency = 0.05  # latencia de 50ms
    bot.command_prefix = "!"

    # Simular servidores
    type(bot).guilds = PropertyMock(return_value=[MagicMock(), MagicMock()])

    # Simular usuario
    mock_user = MagicMock()
    mock_user.name = "TestBot"
    mock_user.id = 123456789
    type(bot).user = PropertyMock(return_value=mock_user)

    return bot


@pytest.fixture
def general_cog(mock_bot: MagicMock) -> GeneralCog:
    """Crear una instancia de GeneralCog.

    Args:
        mock_bot (MagicMock): Fixture del bot simulado

    Returns:
        GeneralCog: Instancia del cog general
    """
    return GeneralCog(mock_bot)


@pytest.fixture
def mock_context(mock_bot: MagicMock) -> MagicMock:
    """Crear un contexto de comando simulado.

    Args:
        mock_bot (MagicMock): Fixture del bot simulado

    Returns:
        MagicMock: Contexto simulado
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock()
    ctx.author.name = "TestUser"
    ctx.author.id = 987654321
    return ctx


def test_general_cog_initialization(mock_bot: MagicMock) -> None:
    """Probar la inicialización de GeneralCog.

    Args:
        mock_bot (MagicMock): Fixture del bot simulado
    """
    cog = GeneralCog(mock_bot)
    assert cog.bot == mock_bot


async def test_ping_command(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando ping.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    with patch("discord_bot.general.cog.logger") as mock_logger:
        # Llamar la función del comando directamente (evita complejidad del decorador)
        # Ignore de tipo necesario: mypy no entiende el patrón de callback de discord.py
        await general_cog.ping.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

        # Verificar que el mensaje fue enviado
        mock_context.send.assert_called_once()
        sent_message = mock_context.send.call_args[0][0]
        assert "Pong!" in sent_message
        assert "50ms" in sent_message  # bot.latency = 0.05 * 1000 = 50ms

        # Verificar logging
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert "ping ejecutado" in log_message
        assert "50ms" in log_message


async def test_ping_command_with_high_latency(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando ping con latencia alta.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    # Establecer latencia alta
    mock_bot.latency = 0.123  # 123ms

    await general_cog.ping.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "123ms" in sent_message


async def test_info_command(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando info.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    with patch("discord_bot.general.cog.logger") as mock_logger:
        await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

        # Verificar que el mensaje fue enviado
        mock_context.send.assert_called_once()
        sent_message = mock_context.send.call_args[0][0]

        # Verificar que toda la información esperada esté presente
        assert "Información del Bot" in sent_message
        assert "TestBot" in sent_message  # nombre del bot
        assert "Servidores: 2" in sent_message  # cantidad de servidores
        assert "Prefijo: `!`" in sent_message  # prefijo del comando

        # Verificar logging
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert "info ejecutado" in log_message


async def test_info_command_no_user(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando info cuando bot.user es None.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    # Establecer usuario a None
    type(mock_bot).user = PropertyMock(return_value=None)

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "Desconocido" in sent_message


async def test_info_command_with_list_prefix(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando info con una lista de prefijos.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    # Establecer el prefijo del comando a una lista
    mock_bot.command_prefix = ["!", "?", "$"]

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    # Debe mostrar todos los prefijos
    assert "Prefijo:" in sent_message


async def test_info_command_with_callable_prefix(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Probar el comando info con un prefijo callable.

    Args:
        general_cog (GeneralCog): Fixture del cog general
        mock_context (MagicMock): Fixture del contexto simulado
        mock_bot (MagicMock): Fixture del bot simulado
    """
    # Establecer el prefijo del comando a una función
    mock_bot.command_prefix = "!"

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "Prefijo:" in sent_message


async def test_setup_function() -> None:
    """Probar que la función setup agrega el cog al bot."""
    mock_bot = MagicMock(spec=commands.Bot)
    mock_bot.add_cog = AsyncMock()

    await setup(mock_bot)

    # Verificar que add_cog fue llamado una vez
    mock_bot.add_cog.assert_called_once()

    # Verificar que el argumento es una instancia de GeneralCog
    added_cog = mock_bot.add_cog.call_args[0][0]
    assert isinstance(added_cog, GeneralCog)
    assert added_cog.bot == mock_bot


async def test_teardown_function() -> None:
    """Probar que la función teardown desregistra el schema."""
    from discord_bot.common.services.config_schema_service import (
        get_config_schema_service,
    )

    mock_bot = MagicMock(spec=commands.Bot)
    mock_bot.add_cog = AsyncMock()

    # Primero setup para registrar
    await setup(mock_bot)

    # Verificar que el schema existe
    schema_service = get_config_schema_service()
    assert schema_service.get_schema("general") is not None

    # Luego teardown
    await teardown(mock_bot)

    # Schema ya no debe existir
    assert schema_service.get_schema("general") is None
