# Discord Bot Codemaps Index

<!-- Generated: 2026-04-10 | Files scanned: 114 | Token estimate: ~900 -->

**Last Updated:** 2026-04-10
**Version:** 1.1.0
**Language:** Python 3.12+
**Framework:** discord.py 2.x + FastAPI + SQLAlchemy 2.0

## Overview

This is a comprehensive Discord bot with integrated web dashboard. The system features event-driven architecture with pluggable cogs, asynchronous database operations, and a FastAPI-based admin panel with OAuth2 authentication.

## Entry Points

- **Bot:** `/home/xurxogr/code/discord/discord_bot/__main__.py` - CLI launcher (supports config files, env vars)
- **Web Server:** `/home/xurxogr/code/discord/discord_bot/web/app.py` - FastAPI application factory

## Architecture Codemaps

| Document | Focus | Key Topics |
|----------|-------|-----------|
| [architecture.md](./architecture.md) | System design, service boundaries | Bot/Web separation, cog system, database layer |
| [backend.md](./backend.md) | Web endpoints, middleware chain | FastAPI routes, OAuth2 auth, CSRF/rate-limit |
| [cogs.md](./cogs.md) | Discord bot modules, event handlers | Verification, Purge, Stockpile, AutoName cogs |
| [data.md](./data.md) | Database schema, models, migrations | Tables, indexes, relationships, Alembic |
| [dependencies.md](./dependencies.md) | External services, integrations | Discord API, OCR service, OAuth2 provider |

## Project Structure Summary

```
discord_bot/
├── __main__.py                 # Entry point (async launcher)
├── bot.py                      # DiscordBot class, cog loading
├── common/                     # Shared infrastructure
│   ├── core/                   # Settings, logging, app configuration
│   ├── models/                 # SQLAlchemy ORM models
│   ├── services/               # Database, config, event bus
│   ├── schemas/                # Pydantic schemas
│   ├── enums/                  # Event types, config option types
│   └── utils/                  # Utilities (message handling)
├── verification/               # Verification module
│   ├── cog.py                  # Discord event handler
│   ├── service.py              # Database CRUD operations
│   ├── handlers/               # Async event handlers
│   ├── models/                 # VerificationRequest ORM model
│   └── formatters.py           # Embed/message formatting
├── purge/                      # User purge/cleanup module
│   ├── cog.py                  # Commands and events
│   ├── service.py              # Business logic
│   ├── models/                 # PurgeRecord, PurgeUserResult
│   ├── execution.py            # Purge execution engine
│   └── views.py                # Button views for confirmations
├── stockpile/                  # Stockpile management module
│   ├── cog.py                  # Commands for stockpile CRUD
│   ├── service.py              # Business logic
│   ├── models/                 # Stockpile ORM model
│   ├── formatters.py           # Embed formatting
│   └── config.py               # Config schema with sections
├── autoname/                   # Automatic username management
│   ├── cog.py                  # Auto-rename on join
│   └── service.py              # Name formatting logic
└── web/                        # FastAPI dashboard
    ├── app.py                  # App factory, middleware setup
    ├── auth/                   # OAuth2 with Discord
    ├── middleware/             # Security, rate limiting, CSRF
    ├── routers/                # API endpoints
    ├── templates/              # Jinja2 HTML templates
    └── static/                 # CSS, JavaScript
```

## Key Patterns

### Clean Architecture
- **Cogs** = thin Discord I/O handlers (events, commands)
- **Services** = business logic (validation, state transitions)
- **Models** = ORM entities (SQLAlchemy 2.0 with async)
- **Schemas** = Pydantic validators for config

### Event Bus Pattern
Event-driven communication between services via `EventBus` (pub/sub)

### Repository Pattern
Services encapsulate DB operations behind stable interfaces:
```python
# DatabaseService -> AsyncSession -> SQLAlchemy models
# ConfigService -> GuildConfig model (get/set/delete)
# VerificationService -> VerificationRequest model (CRUD)
# StockpileService -> Stockpile model (CRUD)
```

### Configuration
Hierarchical config loading:
1. Environment variables (highest priority)
2. JSON config file (`~/.config/discord-bot/config.json`)
3. Defaults in Pydantic models

## Data Flow

### Discord Event → State Change
```
Discord.py event
  ↓
Cog handler (thin wrapper)
  ↓
Service method (business logic)
  ↓
Database write (SQLAlchemy)
  ↓
Event bus publication (notify other services)
```

### Web Request → Response
```
HTTP request
  ↓
Auth middleware (OAuth session)
  ↓
Route handler
  ↓
Service/Database query
  ↓
Template render / JSON response
```

## Dependencies Overview

### Core Runtime
- **discord.py** 2.x - Discord bot framework
- **FastAPI** - Web server
- **SQLAlchemy** 2.0 - Async ORM
- **Pydantic** 2.x - Config & validation
- **httpx** - Async HTTP client

### Database
- **aiosqlite** - Async SQLite driver
- **asyncpg** - Async PostgreSQL driver (optional)
- **Alembic** - Schema migrations

### Utilities
- **uvicorn** - ASGI server
- **Jinja2** - Template engine
- **python-multipart** - Form parsing

## Deployment

### Docker
- `Dockerfile` - Multi-stage build (Python slim base)
- `docker-compose.yml` - Bot + optional PostgreSQL
- Health check endpoint: `/health`

### Configuration
- `.env` file support
- Environment variable overrides
- JSON config file (~/.config/discord-bot/config.json)

## Recent Changes (Since 2026-03-27)

**New Cog: Stockpile Management**
- Fully featured stockpile CRUD with embed formatting
- Config options organized into sections (General, Display, Notifications)
- Comprehensive command set (/stockpile_add, /stockpile_show, /stockpile_delete)

**Verification Improvements**
- Refactored mod message updates to preserve existing data
- Regiment comparison using IDs (prevents OCR character issues)
- Panel recreation prevention when disabled

## Related Documentation

- [README.md](/home/xurxogr/code/discord/README.md) - Feature overview, quick start
- [CONTRIBUTING.md](/home/xurxogr/code/discord/CONTRIBUTING.md) - Development guidelines
- [alembic/](../../../alembic/) - Database migrations
