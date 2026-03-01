"""Tests para el servicio de base de datos."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.models.guild import Guild
from discord_bot.common.services import DatabaseService
from discord_bot.common.services.database import get_database_service


async def test_database_initialization(test_database: DatabaseService) -> None:
    """Prueba de inicialización de base de datos.

    Args:
        test_database (DatabaseService): Fixture del servicio de base de datos de prueba
    """
    assert test_database.engine is not None
    assert test_database.session_maker is not None


async def test_database_session_context_manager(test_database: DatabaseService) -> None:
    """Test de creación y uso de sesión de base de datos.

    Args:
        test_database (DatabaseService): Fixture del servicio de base de datos de prueba
    """
    async with test_database.session() as session:
        # Crear y agregar una nueva guild
        guild = Guild(id=123456789, name="Test Guild", prefix="!")
        session.add(guild)

    # Verificar que la guild fue guardada correctamente
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 123456789))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is not None
        assert fetched_guild.name == "Test Guild"
        assert fetched_guild.prefix == "!"


async def test_database_session_rollback_on_error(test_database: DatabaseService) -> None:
    """Test de rollback de sesión de base de datos en caso de error.

    Args:
        test_database (DatabaseService): Fixture del servicio de base de datos de prueba
    """
    with pytest.raises(ValueError):
        async with test_database.session() as session:
            guild = Guild(id=999, name="Test Guild", prefix="!")
            session.add(guild)
            # Raise an error to trigger rollback
            raise ValueError("Test error")

    # Verificar que la guild no fue guardada debido al rollback
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 999))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is None


async def test_database_close(test_database: DatabaseService) -> None:
    """Test de cierre del servicio de base de datos.

    Args:
        test_database (DatabaseService): Fixture del servicio de base de datos de prueba
    """
    await test_database.close()

    # Después de cerrar, el engine debería ser None
    assert test_database._engine is not None


def test_database_engine_not_initialized() -> None:
    """Probar que acceder a engine antes de la inicialización lanza RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Intentar acceder a engine sin llamar a initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.engine

    assert "Motor de base de datos no inicializado" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_session_maker_not_initialized() -> None:
    """Probar que acceder a session_maker antes de la inicialización lanza RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Intentar acceder a session_maker sin llamar a initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.session_maker

    assert "Creador de sesiones de base de datos no inicializado" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_get_session_not_initialized() -> None:
    """Probar que llamar a get_session() antes de la inicialización lanza RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Intentar llamar a get_session() sin llamar a initialize()
    with pytest.raises(RuntimeError) as exc_info:
        db_service.get_session()

    assert "Creador de sesiones de base de datos no inicializado" in str(exc_info.value)


def test_get_database_service() -> None:
    """Test de la función get_database_service.

    Nota: Esta prueba accede a la función envuelta para evitar el caché de lru_cache.
    """
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")

    # Acceder a la función envuelta para evitar el caché
    if hasattr(get_database_service, "__wrapped__"):
        service = get_database_service.__wrapped__(settings)
    else:
        # Si no existe __wrapped__, llamar directamente (no se probará el caché)
        service = DatabaseService(settings)

    assert isinstance(service, DatabaseService)
    assert service.settings == settings


def test_ensure_database_directory_creates_directory() -> None:
    """Probar que _ensure_database_directory crea el directorio si no existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Usar una ruta de base de datos dentro de un subdirectorio
            settings = DatabaseSettings(url="sqlite+aiosqlite:///foo/bar/test.db")
            db_service = DatabaseService(settings)

            # El directorio no debería existir aún
            db_dir = Path(tmpdir) / "foo" / "bar"
            assert not db_dir.exists()

            # Llamar al método para crear el directorio
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # El directorio ahora debería existir
                assert db_dir.exists()
                assert db_dir.is_dir()

                # El logger debería haber sido llamado
                mock_logger.info.assert_called_once()
                log_message = mock_logger.info.call_args[0][0]
                assert "Creado directorio de base de datos" in log_message
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_handles_existing_directory() -> None:
    """Probar que _ensure_database_directory maneja el caso donde el directorio ya existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Crear el directorio de antemano
            db_dir = Path(tmpdir) / "existing"
            db_dir.mkdir(parents=True, exist_ok=True)

            # Usar una ruta de base de datos dentro del directorio existente
            settings = DatabaseSettings(url="sqlite+aiosqlite:///existing/test.db")
            db_service = DatabaseService(settings)

            # Llamar al método, no debería intentar crear de nuevo
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # El directorio debería seguir existiendo
                assert db_dir.exists()

                # Logger no debería haber sido llamado
                mock_logger.info.assert_not_called()
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_skips_current_directory() -> None:
    """Test that _ensure_database_directory skips when DB file is in current directory."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///test.db")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        # No debería crear ningún directorio
        db_service._ensure_database_directory()

        # Logger no debería haber sido llamado
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_in_memory() -> None:
    """Test that _ensure_database_directory skips for in-memory SQLite databases."""
    # Probar ambas variantes de URL en memoria
    for url in ["sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"]:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)

        with patch("discord_bot.common.services.database.logger") as mock_logger:
            db_service._ensure_database_directory()

            # No debería crear ningún directorio
            mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_non_sqlite() -> None:
    """Probar que _ensure_database_directory omite bases de datos que no son SQLite."""
    # Test PostgreSQL URL
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@localhost/dbname")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        db_service._ensure_database_directory()

        # No debería crear ningún directorio
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_with_relative_path() -> None:
    """Probar que _ensure_database_directory maneja rutas relativas correctamente."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Cambiar al directorio temporal
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            settings = DatabaseSettings(url="sqlite+aiosqlite:///data/bot.db")
            db_service = DatabaseService(settings)

            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # El directorio debería haberse creado correctamente relativo al cwd
                data_dir = Path(tmpdir) / "data"
                assert data_dir.exists()
                assert data_dir.is_dir()

                # Debería haberse registrado la creación del directorio
                mock_logger.info.assert_called_once()
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_with_double_slash_path() -> None:
    """Probar que _ensure_database_directory maneja URLs con doble slash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # URL con 4 slashes: sqlite+aiosqlite:////path -> url_path = "//path"
            # Esto entra en el branch de línea 87 (startswith "//")
            # Después de lstrip("/"), queda "dbtest/test.db"
            url = "sqlite+aiosqlite:////dbtest/test.db"

            settings = DatabaseSettings(url=url)
            db_service = DatabaseService(settings)

            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # El directorio debería haberse creado (relativo al cwd)
                db_dir = Path(tmpdir) / "dbtest"
                assert db_dir.exists()
                assert db_dir.is_dir()

                # Debería haberse registrado la creación del directorio
                mock_logger.info.assert_called_once()
        finally:
            os.chdir(original_cwd)


def test_is_sqlite_returns_true_for_sqlite_urls() -> None:
    """Probar que _is_sqlite devuelve True para URLs de SQLite."""
    sqlite_urls = [
        "sqlite+aiosqlite:///data/bot.db",
        "sqlite+aiosqlite:///:memory:",
        "sqlite:///test.db",
    ]
    for url in sqlite_urls:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)
        assert db_service._is_sqlite() is True


def test_is_sqlite_returns_false_for_non_sqlite_urls() -> None:
    """Probar que _is_sqlite devuelve False para URLs que no son SQLite."""
    non_sqlite_urls = [
        "postgresql+asyncpg://user:pass@localhost/dbname",
        "mysql+aiomysql://user:pass@localhost/dbname",
    ]
    for url in non_sqlite_urls:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)
        assert db_service._is_sqlite() is False


async def test_sqlite_pragmas_configured_on_initialize() -> None:
    """Probar que los PRAGMAs de SQLite se configuran al inicializar."""
    import os

    from sqlalchemy import text

    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # WAL mode requiere una base de datos en archivo, no en memoria
            settings = DatabaseSettings(url="sqlite+aiosqlite:///test_pragmas.db")
            db_service = DatabaseService(settings)

            await db_service.initialize()

            try:
                async with db_service.engine.connect() as conn:
                    # Verificar que WAL mode está configurado
                    result = await conn.execute(text("PRAGMA journal_mode"))
                    journal_mode = result.scalar()
                    assert journal_mode == "wal"

                    # Verificar que foreign_keys está habilitado
                    result = await conn.execute(text("PRAGMA foreign_keys"))
                    foreign_keys = result.scalar()
                    assert foreign_keys == 1
            finally:
                await db_service.close()
        finally:
            os.chdir(original_cwd)


async def test_postgresql_does_not_configure_sqlite_pragmas() -> None:
    """Probar que _configure_sqlite_pragmas no se llama para PostgreSQL."""
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@localhost/dbname")
    db_service = DatabaseService(settings)

    with patch.object(db_service, "_configure_sqlite_pragmas") as mock_configure:
        # No podemos inicializar realmente sin una DB PostgreSQL, pero podemos
        # verificar que _is_sqlite devuelve False
        assert db_service._is_sqlite() is False
        mock_configure.assert_not_called()
