# Discord Bot Skeleton

Un esqueleto de bot de Discord listo para producción con arquitectura basada en características, SQLAlchemy 2.0 y pruebas exhaustivas.

## Características

- 🏗️ **Arquitectura limpia** - Separación de responsabilidades con servicios, modelos y cogs
- 💾 **SQLAlchemy 2.0** - ORM asíncrono moderno con SQLite
- ⚙️ **Configuración con Pydantic** - Gestión de configuración con tipado seguro
- 🧪 **Alta cobertura de tests** - Suite de pruebas exhaustiva con pytest
- 📝 **Docstrings estilo Google** - Documentación profesional
- 🔍 **Type checking estricto** - MyPy con modo estricto
- 🎨 **Calidad de código** - Linting y formateo con Ruff
- 🪝 **Pre-commit hooks** - Comprobaciones automáticas de calidad de código
- 🚌 **Event bus** - Comunicación desacoplada entre servicios
- 📊 **Monitoreo del event loop** - Detecta operaciones bloqueantes en producción
- 🔌 **Multi-interfaz** - Servicios agnósticos del framework para futuro soporte de API

## Inicio Rápido

```bash
# Instalar
python3.12 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Configurar (ver docs/setup.md para detalles)
export BOT__TOKEN="TU_TOKEN_DEL_BOT"

# Ejecutar
7hpbot
```

**Para instrucciones completas de instalación, configuración y solución de problemas, consulta [docs/setup.md](docs/setup.md)**

## Arquitectura

### Principios Clave

- **Servicios agnósticos del framework** - Pueden ser usados por Discord, FastAPI, CLI, etc.
- **Event bus** - Comunicación desacoplada entre servicios
- **Cogs delgados** - Solo manejan I/O de Discord, delegan a servicios
- **Carpeta common** - Infraestructura compartida (settings, database, event bus)
- **Carpetas de características** - Código específico (models, services, cog)

## Añadir Nuevas Características

**Antes de empezar, revisa [docs/contributing.md](docs/contributing.md) para conocer las reglas críticas sobre operaciones bloqueantes, arquitectura y mejores prácticas.**

### Característica Simple (Solo Comandos)

1. Crear `discord_bot/micaracteristica/cog.py`:

```python
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class MiCaracteristicaCog(commands.Cog):
    """Cog de mi característica."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    async def micomando(self, ctx: commands.Context) -> None:
        """Mi comando."""
        await ctx.send("¡Hola!")
        logger.info(f"Comando ejecutado por {ctx.author}")

async def setup(bot: commands.Bot) -> None:
    """Cargar el cog."""
    await bot.add_cog(MiCaracteristicaCog(bot))
```

2. Cargar en `bot.py`: Añadir `"discord_bot.micaracteristica.cog"` a la lista `cogs_to_load`

### Característica Compleja (Con Lógica de Negocio y Event Bus)

Para características con lógica de negocio, usa el **patrón híbrido**:
- **Llamadas directas** para petición/respuesta (cog → servicio)
- **Event bus** para efectos secundarios y comunicación entre servicios

#### 1. Crear el Servicio (Agnóstico del Framework)

```python
# discord_bot/micaracteristica/services/mi_servicio.py
from discord_bot.common.services.event_bus import get_event_bus
from discord_bot.common.enums.event_type import EventType

class MiServicio:
    """Lógica de negocio para mi característica."""

    def __init__(self, database):
        self.db = database
        self.event_bus = get_event_bus()

    async def procesar_item(self, user_id: str, item_data: dict) -> dict:
        """Procesar un item (agnóstico del framework)."""
        # Lógica de negocio principal
        resultado = await self._hacer_procesamiento(item_data)

        # Emitir evento para efectos secundarios
        self.event_bus.emit(EventType.ITEM_PROCESSED, {
            "user_id": user_id,
            "item_id": resultado["id"],
        })

        return resultado
```

#### 2. Crear el Cog (Adaptador Delgado de Discord)

```python
# discord_bot/micaracteristica/cog.py
from discord.ext import commands
from discord_bot.micaracteristica.services import MiServicio

class MiCaracteristicaCog(commands.Cog):
    """Adaptador delgado - solo maneja I/O de Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    async def procesar(self, ctx: commands.Context, item: str) -> None:
        """Procesar un item."""
        # Llamar al servicio (directo)
        servicio = MiServicio(self.bot.database)
        resultado = await servicio.procesar_item(
            user_id=str(ctx.author.id),
            item_data={"name": item}
        )

        # Responder al usuario
        await ctx.send(f"Procesado: {resultado['id']}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiCaracteristicaCog(bot))
```

#### 3. Crear Servicios de Efectos Secundarios (Opcional)

```python
# discord_bot/notificaciones/services/servicio_notificaciones.py
from discord_bot.common.services.event_bus import get_event_bus
from discord_bot.common.enums.event_type import EventType

class ServicioNotificaciones:
    """Escucha eventos y envía notificaciones."""

    def __init__(self, discord_client):
        self.client = discord_client
        event_bus = get_event_bus()
        event_bus.subscribe(EventType.ITEM_PROCESSED, self.on_item_procesado)

    async def on_item_procesado(self, data: dict) -> None:
        """Reaccionar al procesamiento de items."""
        await self.client.send_notification(
            f"¡El item {data['item_id']} fue procesado!"
        )
```

#### 4. Añadir Tests

```python
# tests/micaracteristica/test_servicio.py
async def test_procesar_item():
    servicio = MiServicio(mock_db)
    resultado = await servicio.procesar_item("usuario123", {"name": "test"})
    assert resultado["id"] is not None
```

**Para estrategias de testing completas, objetivos de cobertura y mejores prácticas, consulta [docs/testing.md](docs/testing.md)**

## Documentación

- **[Guía de Configuración](docs/setup.md)** - Instalación y configuración
- **[Guía de Testing](docs/testing.md)** - Filosofía de testing y mejores prácticas
- **[Guía de Contribución](docs/contributing.md)** - Calidad de código y mejores prácticas

## Licencia

MIT
