# Discord Bot

Discord bot with user verification system, role management, stockpile tracking, and web administration panel.

**Last Updated:** 2026-04-24

## Features

- **User Verification** - Screenshot-based verification with optional OCR integration
- **User Purge** - Bulk role management and inactive user cleanup
- **Stockpile Management** - Inventory tracking with embeds and configurable notifications
- **Auto-Name** - Automatic username management based on rules
- **Web Dashboard** - FastAPI-based configuration interface with OAuth2 authentication
- **Database** - Async SQLAlchemy 2.0 (SQLite or PostgreSQL)
- **Clean Architecture** - Framework-agnostic services, thin cogs
- **Event Bus** - Decoupled inter-service communication
- **High Test Coverage** - Comprehensive pytest test suite (98%+)

## Quick Start

```bash
# Clone and install
git clone <repo>
cd discord-bot
python3.12 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Configure (option 1: environment variables)
export BOT__TOKEN="YOUR_BOT_TOKEN"

# Configure (option 2: JSON file)
mkdir -p ~/.config/discord-bot
cp docs/config/config.example.json ~/.config/discord-bot/config.json
# Edit config.json with your token

# For web dashboard (optional)
export WEB__ENABLED="true"
export WEB__SECRET_KEY="random-secret-key"
export WEB__CLIENT_ID="YOUR_CLIENT_ID"
export WEB__CLIENT_SECRET="YOUR_CLIENT_SECRET"

# Run migrations
alembic upgrade head

# Run the bot
discord-bot
```

## Configuration

Configuration can be set via:
1. **Environment variables** (highest priority)
2. **`.env` file** in working directory
3. **JSON file** at `~/.config/discord-bot/config.json`

See [docs/config/config.example.json](docs/config/config.example.json) for a complete example.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT__TOKEN` | Discord bot token | (required) |
| `BOT__COMMAND_PREFIX` | Command prefix | `!` |
| `BOT__OWNER_ID` | Bot owner ID | `null` |
| `DATABASE__URL` | Database connection URL | `sqlite+aiosqlite:///data/bot.db` |
| `DATABASE__ECHO` | Log SQL queries | `false` |
| `WEB__ENABLED` | Enable web dashboard | `false` |
| `WEB__HOST` | Web server host | `0.0.0.0` |
| `WEB__PORT` | Web server port | `8000` |
| `WEB__SECRET_KEY` | Session secret key | (required if web) |
| `WEB__CLIENT_ID` | Discord OAuth2 Client ID | (required if web) |
| `WEB__CLIENT_SECRET` | Discord OAuth2 Client Secret | (required if web) |
| `WEB__REDIRECT_URI` | OAuth2 callback URI | `http://localhost:8000/auth/callback` |
| `WEB__OWNER_IDS` | Admin user IDs (JSON array) | `[]` |
| `WEB__HTTPS_ONLY` | HTTPS-only cookies | `true` |
| `VERIFICATION__API_URL` | OCR verification API URL | (empty) |
| `VERIFICATION__API_KEY` | OCR verification API key | (empty) |
| `VERIFICATION__API_TIMEOUT` | API timeout in seconds | `30` |
| `LOGGING__LOG_LEVEL` | Log level | `INFO` |
| `LOGGING__LOG_FILE` | Log file path | `null` |

### Database

SQLite is used by default. For PostgreSQL:

```bash
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/dbname"
```

## Modules

### Verification

Screenshot-based user verification system:

- Verification panel with buttons (member/ally)
- DM instructions to users
- Mod channel with configurable embeds
- Optional OCR API integration for automatic verification
  - Per-reason auto-rejection toggles (6 configurable rejection reasons)
  - Check faction, shard, regiment, name matching, screenshot age, API validity
- User verification history
- Pending verification tracker
- Race condition protection for rapid interaction clicks

### Purge

Bulk user and role management:

- Purge users without specific roles
- Purge by inactivity
- Moderator confirmation before execution
- Result logging

### Stockpile

Inventory and stockpile management:

- Create, update, and delete stockpiles with commands
- Display stockpiles in formatted embeds
- Configurable notifications on stockpile changes
- Config sections: General, Display, Notifications
- Placeholder support for customization

### Reaction Roles

Emoji-based role assignment system:

- Reaction-triggered role assignment
- Custom emoji support
- Per-server configuration

### Auto-Name

Automatic username management:

- Rule-based automatic renaming
- Per-server configuration

### Web Dashboard

Administration interface at `http://localhost:8000`:

- Discord OAuth2 authentication
- Per-server module configuration
- Embed editor with preview
- Role and channel management

## Architecture

```
discord_bot/
├── common/           # Shared infrastructure
│   ├── core/         # Settings, logging, app configuration
│   ├── models/       # SQLAlchemy ORM models
│   ├── services/     # Database, config, event bus
│   ├── schemas/      # Pydantic schemas
│   └── enums/        # Event types, config option types
├── verification/     # Verification module
│   ├── cog.py        # Discord event handler
│   ├── handlers/     # Async event handlers
│   ├── service.py    # Database CRUD operations
│   ├── formatters.py # Embed/message formatting
│   └── models/       # VerificationRequest ORM model
├── purge/            # Purge module
├── stockpile/        # Stockpile management module
├── autoname/         # Auto-name module
└── web/              # Administration panel
    ├── app.py        # FastAPI application
    ├── routers/      # API endpoints
    ├── auth/         # OAuth2 authentication
    ├── middleware/   # Security, rate limiting, CSRF
    └── templates/    # Jinja2 templates
```

### Design Principles

- **Framework-agnostic services** - Business logic doesn't depend on Discord
- **Thin cogs** - Only handle Discord I/O, delegate to services
- **Event bus** - Decoupled communication between modules
- **Typed configuration** - Pydantic for validation and settings
- **IDOR prevention** - Non-sequential public IDs (NanoID) for external interfaces

## Documentation

| Document | Description |
|----------|-------------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, testing, code standards |
| [RUNBOOK.md](RUNBOOK.md) | Deployment, monitoring, troubleshooting |
| [docs/CODEMAPS/](docs/CODEMAPS/) | Architecture documentation for AI context |

### Codemaps

Token-lean architecture documentation optimized for AI assistants:

- [INDEX.md](docs/CODEMAPS/INDEX.md) - Project overview and entry points
- [architecture.md](docs/CODEMAPS/architecture.md) - System design, service boundaries
- [backend.md](docs/CODEMAPS/backend.md) - Web API routes, middleware chain
- [cogs.md](docs/CODEMAPS/cogs.md) - Discord bot modules, event handlers
- [data.md](docs/CODEMAPS/data.md) - Database schema, models, migrations
- [dependencies.md](docs/CODEMAPS/dependencies.md) - External services, integrations

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=discord_bot

# Linting
ruff check .

# Type checking
mypy discord_bot

# Formatting
ruff format .

# Security audit
pip-audit
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Deployment

See [RUNBOOK.md](RUNBOOK.md) for:

- Docker deployment with PostgreSQL
- Production security configuration
- Health checks and monitoring
- Database backup and maintenance
- Troubleshooting common issues

### Quick Docker Deploy

```bash
# Create config
cp .env.example .env
cp docs/config/config.example.json config/config.json
# Edit both files with your values

# Start services
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs bot
```

## License

MIT
