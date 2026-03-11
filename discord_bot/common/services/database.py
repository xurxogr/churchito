"""Servicio de base de datos para gestionar conexiones de SQLAlchemy."""

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from discord_bot.common.core.settings.database import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Servicio para gestionar conexiones a la base de datos."""

    def __init__(self, settings: DatabaseSettings) -> None:
        """Inicializar el servicio de base de datos.

        Args:
            settings (DatabaseSettings): Configuración de la base de datos
        """
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Obtener el motor de la base de datos.

        Returns:
            AsyncEngine: motor asíncrono de SQLAlchemy

        Raises:
            RuntimeError: Si el motor no está inicializado
        """
        if self._engine is None:
            raise RuntimeError(
                "Motor de base de datos no inicializado. Llama a initialize() primero."
            )
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Obtener el creador de sesiones.

        Returns:
            async_sessionmaker[AsyncSession]: creador de sesiones asíncronas de SQLAlchemy

        Raises:
            RuntimeError: Si el creador de sesiones no está inicializado
        """
        if self._session_maker is None:
            raise RuntimeError(
                "Creador de sesiones de base de datos no inicializado. "
                "Llama a initialize() primero."
            )
        return self._session_maker

    def _ensure_database_directory(self) -> None:
        """Asegurar que el directorio de la base de datos existe (solo para SQLite)."""
        # Parse URL to check if it's SQLite
        if not self.settings.url.startswith("sqlite"):
            return

        # Extract file path from SQLite URL
        # Format: sqlite+aiosqlite:///data/bot.db or sqlite:///data/bot.db
        # After split: /data/bot.db (single slash for relative, // for absolute)
        url_path = self.settings.url.split("://", 1)[-1]

        # Skip if in-memory database
        if url_path == ":memory:" or url_path.endswith(":memory:"):
            return

        # Handle absolute vs relative paths
        # sqlite://localhost//absolute/path -> //absolute/path (absolute)
        # sqlite:///relative/path -> /relative/path (relative on Unix, need to strip /)
        if url_path.startswith("//"):
            # Absolute path with host
            db_path = Path(url_path.lstrip("/"))
        else:
            # Relative path - strip single leading slash
            db_path = Path(url_path.lstrip("/"))

        # Create parent directory if it doesn't exist
        db_dir = db_path.parent
        if db_dir and str(db_dir) != "." and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Creado directorio de base de datos: {db_dir}")

    def _redact_url(self, url: str) -> str:
        """Redactar credenciales de una URL de base de datos.

        Args:
            url (str): URL de conexión

        Returns:
            str: URL con credenciales redactadas
        """
        # Redact password in URLs like: postgresql+asyncpg://user:password@host:port/db
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

    def _is_sqlite(self) -> bool:
        """Verificar si la base de datos es SQLite.

        Returns:
            bool: True si es SQLite
        """
        return self.settings.url.startswith("sqlite")

    def _configure_sqlite_pragmas(self, engine: AsyncEngine) -> None:
        """Configurar PRAGMAs de SQLite para mejor rendimiento y consistencia.

        Args:
            engine: Motor de SQLAlchemy
        """

        def set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # WAL mode: mejor rendimiento en lecturas/escrituras concurrentes
            cursor.execute("PRAGMA journal_mode=WAL")
            # Habilitar foreign keys (deshabilitadas por defecto en SQLite)
            cursor.execute("PRAGMA foreign_keys=ON")
            # Timeout para esperar cuando la BD está bloqueada (5 segundos)
            cursor.execute("PRAGMA busy_timeout=5000")
            # Modo synchronous NORMAL es seguro con WAL y más rápido
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        # El evento se registra en el sync_engine subyacente
        event.listen(engine.sync_engine, "connect", set_sqlite_pragma)

    async def initialize(self) -> None:
        """Inicializar el motor de la base de datos y el creador de sesiones."""
        logger.info(f"Inicializando base de datos: {self._redact_url(self.settings.url)}")

        # Ensure database directory exists (for SQLite)
        self._ensure_database_directory()

        self._engine = create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            pool_recycle=self.settings.pool_recycle,
        )

        # Configurar PRAGMAs para SQLite
        if self._is_sqlite():
            self._configure_sqlite_pragmas(self._engine)

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Verify connection works
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Base de datos inicializada con éxito")
        except Exception as e:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None
            raise RuntimeError(f"No se pudo conectar a la base de datos: {e}") from e

    async def close(self) -> None:
        """Cerrar conexiones de base de datos."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Conexiones de base de datos cerradas")

    def get_session(self) -> AsyncSession:
        """Obtener una nueva sesión de base de datos.

        Returns:
            AsyncSession: sesión asíncrona de SQLAlchemy

        Nota:
            El llamador es responsable de confirmar/revertir y cerrar la sesión.
        """
        return self.session_maker()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Obtener un gestor de contexto de sesión de base de datos.

        Yields:
            AsyncSession: sesión asíncrona de SQLAlchemy
        """
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@lru_cache
def get_database_service(settings: DatabaseSettings) -> DatabaseService:
    """Obtener el singleton del servicio de base de datos.

    Args:
        settings (DatabaseSettings): Configuración de la base de datos

    Returns:
        DatabaseService: instancia del servicio de base de datos
    """
    return DatabaseService(settings)
