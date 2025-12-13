# Guía de Configuración

## Requisitos Previos

- Python 3.12+
- pip

## Pasos de Instalación

### 1. Crear Entorno Virtual

```bash
cd ~/code/discord
python3.12 -m venv venv
source venv/bin/activate
```

### 2. Instalar Dependencias

```bash
# Instalar en modo desarrollo con dependencias de dev
pip install -e ".[dev]"
```

### 3. Configurar Pre-commit Hooks

```bash
pre-commit install
```

### 4. Configurar el Bot

Crear archivo de configuración:

```bash
mkdir -p ~/.config/discord-bot
```

Crear `~/.config/discord-bot/config.json` con tu token del bot:

```json
{
  "bot": {
    "token": "TU_TOKEN_DE_DISCORD_AQUÍ",
    "command_prefix": "!",
    "owner_id": 123456789,
    "event_loop_warning_threshold": 0.5
  },
  "logging": {
    "log_level": "INFO",
    "log_file": null,
    "rotate_logs": false
  },
  "database": {
    "url": "sqlite+aiosqlite:///data/bot.db"
  }
}
```

O usa variables de entorno:

```bash
export BOT__TOKEN="TU_TOKEN_DE_DISCORD_AQUÍ"
export BOT__COMMAND_PREFIX="!"
export LOGGING__LOG_LEVEL="INFO"
```

### 5. Ejecutar Tests

```bash
# Ejecutar todos los tests
pytest

# Ejecutar con cobertura
pytest --cov=discord_bot --cov-report=html

# Abrir reporte de cobertura
open htmlcov/index.html
```

### 6. Ejecutar el Bot

```bash
7hpbot
```

O usando el módulo de Python:

```bash
python -m discord_bot
```

## Verificación

Para verificar que todo funciona:

1. **Comprobar calidad de código:**
   ```bash
   pre-commit run --all-files
   ```

2. **Ejecutar tests:**
   ```bash
   pytest -v
   ```

3. **Comprobar type hints:**
   ```bash
   mypy discord_bot
   ```

4. **Probar inicio del bot (comando help):**
   ```bash
   7hpbot --help
   ```

## Obtener un Token de Bot de Discord

1. Ve a https://discord.com/developers/applications
2. Haz clic en "New Application"
3. Dale un nombre y créala
4. Ve a la sección "Bot"
5. Haz clic en "Add Bot"
6. Bajo "Token", haz clic en "Copy"
7. Pégalo en tu archivo de configuración

## Invitar el Bot a un Servidor

1. En el Portal de Desarrolladores de Discord, ve a OAuth2 > URL Generator
2. Selecciona scopes: `bot`, `applications.commands`
3. Selecciona permisos del bot: `Send Messages`, `Read Message History`, `Manage Roles`, etc.
4. Copia la URL generada y ábrela en el navegador
5. Selecciona tu servidor y autoriza

## Configuración de Desarrollo

### Estructura del Proyecto

```
discord_bot/
├── common/              # Código compartido e infraestructura
│   ├── core/           # Infraestructura principal
│   │   ├── settings/   # Configuración con Pydantic (bot, database, logging)
│   │   └── logging.py  # Configuración de logging con rotación
│   ├── models/         # Modelos de SQLAlchemy (Base, Guild, etc.)
│   ├── schemas/        # Schemas de Pydantic (UserContext)
│   ├── services/       # Servicios compartidos
│   │   ├── database.py # DatabaseService (SQLAlchemy asíncrono)
│   │   └── event_bus.py # Event bus para pub/sub
│   ├── enums/          # Enums compartidos (EventType)
│   └── decorators.py   # Decoradores reutilizables (timeout, retry)
├── general/            # Cog de comandos generales
│   └── cog.py          # Comandos ping, info
├── __main__.py         # Punto de entrada CLI
└── bot.py              # Clase principal del bot con monitoreo del event loop
```

### Añadir Nuevas Características

1. Crear una nueva carpeta en `discord_bot/` (ej., `discord_bot/micaracteristica/`)
2. Añadir código específico de la característica:
   - `models/` - Modelos de base de datos específicos de la característica
   - `schemas/` - DTOs de Pydantic
   - `services/` - Lógica de negocio
   - `cog.py` - Interfaz de Discord
3. Añadir tests en `tests/micaracteristica/`
4. Cargar el cog en `bot.py`

### Código Compartido vs Específico de Característica

- **Código compartido** (en `common/`): Usado por 2+ características
- **Código de característica** (en carpeta de característica): Usado por 1 característica solamente

## Solución de Problemas

### Los tests fallan con errores de importación
```bash
# Asegúrate de haber instalado en modo editable
pip install -e ".[dev]"
```

### El bot no arranca
```bash
# Verifica que el archivo de configuración existe y tiene un token válido
cat ~/.config/discord-bot/config.json

# O usa variable de entorno
export BOT__TOKEN="tu_token_aquí"
7hpbot
```

### Los pre-commit hooks fallan
```bash
# Instalar dependencias de dev
pip install -e ".[dev]"

# Actualizar hooks
pre-commit autoupdate
```

### Dependencias faltantes
```bash
# Reinstalar todas las dependencias
pip install -e ".[dev]" --force-reinstall
```

## Configuración con Docker

```bash
# Construir imagen
docker build -t discord-bot .

# Ejecutar con configuración montada
docker run -v ~/.config/discord-bot:/root/.config/discord-bot discord-bot

# O con variables de entorno
docker run -e BOT__TOKEN="tu_token" discord-bot
```

## Próximos Pasos

- Lee la [Guía de Testing](testing.md) para mejores prácticas de testing
- Añade características personalizadas en nuevas carpetas de características
- Escribe tests exhaustivos
- Actualiza la documentación
