# Discord Bot

Bot de Discord con sistema de verificación, gestión de roles y panel de administración web.

## Características

- **Verificación de usuarios** - Sistema de verificación con capturas de pantalla y OCR
- **Purga de usuarios** - Gestión masiva de roles y limpieza de usuarios inactivos
- **Auto-nombre** - Gestión automática de nombres de usuario
- **Panel web** - Interfaz de configuración basada en FastAPI con autenticación OAuth2
- **Base de datos** - SQLAlchemy 2.0 asíncrono (SQLite o PostgreSQL)
- **Arquitectura limpia** - Servicios agnósticos del framework, cogs delgados
- **Event bus** - Comunicación desacoplada entre servicios
- **Alta cobertura de tests** - Suite de pruebas exhaustiva con pytest

## Inicio Rápido

```bash
# Clonar e instalar
git clone <repo>
cd discord-bot
python3.12 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Configurar (opción 1: variables de entorno)
export BOT__TOKEN="TU_TOKEN_DEL_BOT"

# Configurar (opción 2: archivo JSON)
mkdir -p ~/.config/discord-bot
cp docs/config/config.example.json ~/.config/discord-bot/config.json
# Editar config.json con tu token

# Para el panel web (opcional)
export WEB__ENABLED="true"
export WEB__SECRET_KEY="clave-secreta-aleatoria"
export WEB__CLIENT_ID="TU_CLIENT_ID"
export WEB__CLIENT_SECRET="TU_CLIENT_SECRET"

# Ejecutar migraciones
alembic upgrade head

# Ejecutar el bot
discord-bot
```

## Configuración

La configuración se puede hacer mediante:
1. **Variables de entorno** (mayor prioridad)
2. **Archivo `.env`** en el directorio de trabajo
3. **Archivo JSON** en `~/.config/discord-bot/config.json`

Ver [docs/config/config.example.json](docs/config/config.example.json) para un ejemplo completo.

### Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `BOT__TOKEN` | Token del bot de Discord | (requerido) |
| `BOT__COMMAND_PREFIX` | Prefijo para comandos | `!` |
| `BOT__OWNER_ID` | ID del propietario del bot | `null` |
| `DATABASE__URL` | URL de conexión a la base de datos | `sqlite+aiosqlite:///data/bot.db` |
| `DATABASE__ECHO` | Mostrar queries SQL | `false` |
| `WEB__ENABLED` | Habilitar panel web | `false` |
| `WEB__HOST` | Host del servidor web | `0.0.0.0` |
| `WEB__PORT` | Puerto del servidor web | `8000` |
| `WEB__SECRET_KEY` | Clave secreta para sesiones | (requerido si web) |
| `WEB__CLIENT_ID` | Client ID de OAuth2 de Discord | (requerido si web) |
| `WEB__CLIENT_SECRET` | Client Secret de OAuth2 | (requerido si web) |
| `WEB__REDIRECT_URI` | URI de callback OAuth2 | `http://localhost:8000/auth/callback` |
| `WEB__OWNER_IDS` | IDs con acceso admin (JSON array) | `[]` |
| `WEB__HTTPS_ONLY` | Cookie solo sobre HTTPS | `true` |
| `VERIFICATION__API_URL` | URL de la API de verificación OCR | (vacío) |
| `VERIFICATION__API_KEY` | API key para verificación OCR | (vacío) |
| `VERIFICATION__API_TIMEOUT` | Timeout en segundos | `30` |
| `LOGGING__LOG_LEVEL` | Nivel de log | `INFO` |
| `LOGGING__LOG_FILE` | Archivo de log | `null` |

### Base de Datos

Por defecto usa SQLite. Para PostgreSQL:

```bash
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/dbname"
```

## Módulos

### Verificación

Sistema de verificación de usuarios mediante capturas de pantalla:

- Panel de verificación con botones (miembro/aliado)
- Instrucciones por DM al usuario
- Canal de moderación con embeds configurables
- Integración opcional con API OCR para verificación automática
- Historial de verificaciones por usuario
- Tracker de verificaciones pendientes

### Purga

Gestión masiva de usuarios y roles:

- Purga de usuarios sin roles específicos
- Purga por inactividad
- Confirmación de moderadores antes de ejecutar
- Registro de resultados

### Auto-nombre

Gestión automática de nombres de usuario:

- Renombrado automático basado en reglas
- Configuración por servidor

### Panel Web

Interfaz de administración accesible en `http://localhost:8000`:

- Autenticación OAuth2 con Discord
- Configuración de cada módulo por servidor
- Editor de embeds con vista previa
- Gestión de roles y canales

## Arquitectura

```
discord_bot/
├── common/           # Infraestructura compartida
│   ├── database/     # Conexión y modelos base
│   ├── services/     # Servicios comunes (config, embed builder)
│   ├── schemas/      # Esquemas Pydantic
│   └── enums/        # Enumeraciones
├── verification/     # Módulo de verificación
│   ├── cog.py        # Cog de Discord
│   ├── handlers.py   # Lógica de manejo de eventos
│   ├── service.py    # Servicio de base de datos
│   ├── formatters.py # Construcción de embeds
│   └── config.py     # Esquema de configuración
├── purga/            # Módulo de purga
├── autoname/         # Módulo de auto-nombre
└── web/              # Panel de administración
    ├── app.py        # Aplicación FastAPI
    ├── routers/      # Endpoints
    ├── auth/         # Autenticación OAuth2
    └── templates/    # Plantillas Jinja2
```

### Principios

- **Servicios agnósticos** - La lógica de negocio no depende de Discord
- **Cogs delgados** - Solo manejan I/O de Discord, delegan a servicios
- **Event bus** - Comunicación desacoplada entre módulos
- **Configuración tipada** - Pydantic para validación y settings

## Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Ejecutar tests
pytest

# Ejecutar tests con cobertura
pytest --cov=discord_bot

# Linting
ruff check .

# Type checking
mypy discord_bot

# Formateo
ruff format .
```

## Licencia

MIT
