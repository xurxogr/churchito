# Discord Bot Operations Runbook

This guide covers deployment, monitoring, troubleshooting, and common operational tasks.

## Table of Contents

1. [Deployment](#deployment)
2. [Health Checks](#health-checks)
3. [Configuration](#configuration)
4. [Monitoring & Logs](#monitoring--logs)
5. [Troubleshooting](#troubleshooting)
6. [Database Maintenance](#database-maintenance)
7. [Common Issues](#common-issues)

---

## Deployment

### Quick Start with Docker

<!-- AUTO-GENERATED: From docker-compose.yml -->

The easiest way to deploy is using Docker Compose with PostgreSQL:

```bash
# 1. Create environment file
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 2. Create configuration
mkdir -p config
cp docs/config/config.example.json config/config.json
# Edit config/config.json and set your bot token

# 3. Start services
docker-compose up -d

# 4. Check status
docker-compose ps
docker-compose logs bot
```

**Services started:**
- `bot` - Discord bot with FastAPI dashboard (port 8000)
- `db` - PostgreSQL 17 database
- Volumes: `bot_data`, `bot_logs`, `postgres_data`

**Health Check:** The bot includes health check endpoint at `http://localhost:8000/health`

<!-- END AUTO-GENERATED -->

### Python Direct Installation

For development or single-machine deployment:

```bash
# 1. Install dependencies
python3.12 -m venv venv
source venv/bin/activate
pip install -e .

# 2. Configure (see Configuration section below)
export BOT__TOKEN="your_token"
mkdir -p ~/.config/discord-bot
cp docs/config/config.example.json ~/.config/discord-bot/config.json

# 3. Run migrations
alembic upgrade head

# 4. Start the bot
discord-bot
```

### Production Considerations

#### Security

- [ ] Set `WEB__HTTPS_ONLY=true` (requires reverse proxy with SSL)
- [ ] Use strong `WEB__SECRET_KEY` (minimum 32 characters, use `openssl rand -hex 16`)
- [ ] Set `BOT__OWNER_ID` to restrict admin commands
- [ ] Enable rate limiting (default: enabled)
- [ ] Use environment variables for secrets, never commit `.env`

#### Database

- Use PostgreSQL in production (SQLite is for development only)
- Set `DATABASE__URL="postgresql+asyncpg://user:pass@host/db"`
- Enable SSL connection: `DATABASE__URL="postgresql+asyncpg://user:pass@host/db?ssl=require"`
- Regular backups: See [Database Maintenance](#database-maintenance)

#### Performance

- Set `WEB__HOST=0.0.0.0` to accept all connections
- Use reverse proxy (nginx/Caddy) for SSL termination
- Enable connection pooling: `DATABASE__POOL_RECYCLE=3600` (already configured)
- Monitor database connection count

#### Deployment Pipeline

```bash
# 1. Pull latest code
git pull origin main

# 2. Install dependencies
pip install -e .

# 3. Run migrations (safe: non-blocking)
alembic upgrade head

# 4. Restart service
systemctl restart discord-bot
# or for Docker:
docker-compose up -d --no-deps --build bot
```

---

## Health Checks

### Web Dashboard Health Endpoint

```bash
# Check bot is running and responding
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

### Discord Bot Connection

Check logs for successful connection:

```bash
# Docker
docker-compose logs -f bot | grep "ready"

# Direct Python
# Look for log line: "Logged in as BotName#0000"
```

### Database Connection

```bash
# From bot logs - look for migration logs
docker-compose logs bot | grep "alembic\|migration"

# Or test directly
python -c "
import asyncio
from discord_bot.common.services import DatabaseService
from discord_bot.common.core import get_settings

settings = get_settings()
db = DatabaseService(settings.database)
asyncio.run(db.init())
print('Database connection successful')
"
```

### Monitoring Commands

```bash
# Check services are running
docker-compose ps

# View logs in real-time
docker-compose logs -f bot

# Check resource usage
docker stats

# View database logs
docker-compose logs db | tail -50
```

---

## Configuration

### Environment Variables

<!-- AUTO-GENERATED: From README.md Variables section -->

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BOT__TOKEN` | Discord bot token | (none) | **YES** |
| `BOT__COMMAND_PREFIX` | Prefix for text commands | `!` | No |
| `BOT__OWNER_ID` | Owner ID (for owner-only commands) | `null` | No |
| `DATABASE__URL` | Database connection string | `sqlite+aiosqlite:///data/bot.db` | No |
| `DATABASE__ECHO` | Log SQL queries | `false` | No |
| `WEB__ENABLED` | Enable web dashboard | `false` | No |
| `WEB__HOST` | Web server host | `0.0.0.0` | No |
| `WEB__PORT` | Web server port | `8000` | No |
| `WEB__SECRET_KEY` | Session secret (required if web enabled) | (none) | If `WEB__ENABLED=true` |
| `WEB__CLIENT_ID` | Discord OAuth2 Client ID (required if web enabled) | (none) | If `WEB__ENABLED=true` |
| `WEB__CLIENT_SECRET` | Discord OAuth2 Client Secret (required if web enabled) | (none) | If `WEB__ENABLED=true` |
| `WEB__REDIRECT_URI` | OAuth2 callback URL | `http://localhost:8000/auth/callback` | No |
| `WEB__OWNER_IDS` | JSON array of admin user IDs | `[]` | No |
| `WEB__HTTPS_ONLY` | Require HTTPS for cookies | `true` | No |
| `VERIFICATION__API_URL` | OCR verification API endpoint | (empty) | No |
| `VERIFICATION__API_KEY` | OCR verification API key | (empty) | No |
| `VERIFICATION__API_TIMEOUT` | API timeout in seconds | `30` | No |
| `LOGGING__LOG_LEVEL` | Log level | `INFO` | No |
| `LOGGING__LOG_FILE` | Log file path | `null` | No |

<!-- END AUTO-GENERATED -->

### Configuration File

Alternatively, use JSON configuration at `~/.config/discord-bot/config.json`:

```json
{
  "bot": {
    "token": "YOUR_BOT_TOKEN",
    "command_prefix": "!",
    "owner_id": null,
    "description": "Your bot description",
    "event_loop_warning_threshold": 0.5
  },
  "database": {
    "url": "sqlite+aiosqlite:///data/bot.db",
    "echo": false,
    "pool_recycle": 3600
  },
  "web": {
    "enabled": false,
    "host": "0.0.0.0",
    "port": 8000,
    "secret_key": "change-me-to-random-secret",
    "client_id": "",
    "client_secret": ""
  },
  "logging": {
    "log_level": "INFO",
    "log_file": null
  }
}
```

**Priority order:**
1. Environment variables (highest)
2. JSON configuration file
3. Defaults (lowest)

### Discord OAuth2 Setup

Required for web dashboard authentication:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create or select your application
3. Go to OAuth2 → General
4. Copy **Client ID** and **Client Secret**
5. Add Redirect URL: `http://your-domain:8000/auth/callback` (or `https://` for production)
6. Set environment variables:

```bash
export WEB__ENABLED="true"
export WEB__CLIENT_ID="your_client_id_here"
export WEB__CLIENT_SECRET="your_client_secret_here"
export WEB__REDIRECT_URI="https://your-domain.com/auth/callback"
```

---

## Monitoring & Logs

### Log Levels

```
DEBUG    - Detailed diagnostic information
INFO     - General information (default)
WARNING  - Warning messages
ERROR    - Error messages
CRITICAL - Critical failures
```

Set log level:

```bash
export LOGGING__LOG_LEVEL="DEBUG"
# or in config.json:
# "logging": { "log_level": "DEBUG" }
```

### Log Files

```bash
# Enable file logging
export LOGGING__LOG_FILE="/app/logs/discord-bot.log"

# Or in Docker:
docker-compose exec bot tail -f /app/logs/discord-bot.log
```

### Viewing Logs

```bash
# Docker - live logs
docker-compose logs -f bot

# Docker - last 100 lines
docker-compose logs --tail=100 bot

# Docker - logs from last 30 minutes
docker-compose logs --since=30m bot

# Direct Python
journalctl -u discord-bot -f  # If using systemd

# Log file
tail -f /app/logs/discord-bot.log
```

### Key Log Messages

```
[INFO] discord_bot: Initiating Discord bot...          # Bot starting
[INFO] discord.client: Logged in as BotName#0000       # Connection successful
[ERROR] discord_bot: Fatal error:                       # Critical failure
[WARNING] sqlalchemy.pool: Connection timeout           # Database issues
```

---

## Troubleshooting

### Bot Not Starting

**Check 1: Token is valid**

```bash
# Verify token is set
echo $BOT__TOKEN
# Should output your token, not be empty

# Or check config file
cat ~/.config/discord-bot/config.json | grep token
```

**Check 2: View detailed error**

```bash
# Direct Python (shows full error)
discord-bot --log-level DEBUG

# Docker
docker-compose logs bot | head -50
```

**Check 3: Database connection**

```bash
# SQLite (default)
ls -la data/bot.db

# PostgreSQL
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/discord"
python -c "import asyncio; from discord_bot.common.services import DatabaseService; ..."
```

### Web Dashboard Not Accessible

**Check 1: Port is open**

```bash
# Is something listening on 8000?
lsof -i :8000
# or
netstat -tlnp | grep 8000
```

**Check 2: Dashboard is enabled**

```bash
echo $WEB__ENABLED
# Should be "true"
```

**Check 3: OAuth2 credentials**

```bash
echo $WEB__CLIENT_ID
echo $WEB__CLIENT_SECRET
# Both should be set

# Check redirect URI matches
echo $WEB__REDIRECT_URI
# Should match what's configured in Discord Developer Portal
```

**Check 4: Test endpoint directly**

```bash
curl http://localhost:8000/health
# Should respond with {"status": "ok"}

curl http://localhost:8000/
# Should redirect to /auth/login
```

### Database Connection Timeouts

**For SQLite (development):**

```bash
# SQLite is single-threaded. Increase retry timeout
export DATABASE__POOL_RECYCLE=3600  # Already set by default

# Better: Use PostgreSQL for development
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/discord"
alembic upgrade head
```

**For PostgreSQL:**

```bash
# Check connection string
export DATABASE__URL="postgresql+asyncpg://user:password@host:5432/discord"

# Verify connection
psql -U user -h host -d discord -c "SELECT 1"

# Check connection limits
docker-compose exec db psql -U discord -d discord -c "SELECT count(*) FROM pg_stat_activity;"
```

### Memory Usage Growing

**Check 1: Event bus subscribers**

```bash
# Look for repeated subscriptions in logs
docker-compose logs bot | grep "Subscribe"
# Should see each subscription once during startup

# Fix: Ensure cogs don't subscribe in event handlers
```

**Check 2: Database connection pool**

```bash
# Check active connections
docker-compose exec db psql -U discord -d discord -c "SELECT count(*) FROM pg_stat_activity;"

# Should be < 20 connections
# If high, increase DATABASE__POOL_RECYCLE
```

**Check 3: Restart to clear**

```bash
docker-compose restart bot
# Verify memory drops
docker stats
```

### High CPU Usage

**Common causes:**

1. Busy-loop in async code (blocking calls in async functions)
2. Excessive logging (set `LOGGING__LOG_LEVEL=INFO`)
3. Database query performance

**Diagnose:**

```bash
# Enable query logging
export DATABASE__ECHO=true

# Check logs for slow queries
docker-compose logs bot | grep "SLOW"

# Review database statistics
docker-compose exec db psql -U discord -d discord -c "\d+ verification_requests"
```

### Guild Configuration Not Persisting

**Check 1: Database writes**

```bash
# Enable SQL echo to see writes
export DATABASE__ECHO=true

# Check database has data
docker-compose exec db psql -U discord -d discord -c "SELECT * FROM guild_configs LIMIT 5;"
```

**Check 2: Permissions**

```bash
# Verify bot has necessary intents enabled
# In Discord Developer Portal:
# Settings → Bot → Intents
# - Server Members Intent: ON
# - Message Content Intent: ON (for text commands)

# Verify bot has permissions in guild
# Server Settings → Roles → @BotName
# Ensure sufficient permissions
```

**Check 3: Cog loading**

```bash
# Check cog is loaded
docker-compose logs bot | grep "Loaded cog"

# Should see: "Loaded cog: verification", etc.
```

---

## Database Maintenance

### Backup PostgreSQL

```bash
# One-time backup
docker-compose exec db pg_dump -U discord discord > backup-$(date +%Y%m%d).sql

# Automated daily backup (add to crontab)
0 2 * * * docker-compose -f /path/to/docker-compose.yml exec -T db pg_dump -U discord discord > /backups/discord-$(date +\%Y\%m\%d).sql
```

### Restore PostgreSQL

```bash
# Stop the bot (don't write while restoring)
docker-compose stop bot

# Restore from backup
docker-compose exec db psql -U discord discord < backup-20260311.sql

# Restart
docker-compose up -d bot
```

### Migrate SQLite to PostgreSQL

Use the provided migration script:

```bash
# 1. Set up PostgreSQL database
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/discord"
alembic upgrade head

# 2. Run migration script
python scripts/migrate_postgres_to_sqlite.py \
    --source sqlite+aiosqlite:///data/bot.db \
    --target "postgresql+asyncpg://user:pass@localhost/discord"

# 3. Verify data
docker-compose exec db psql -U discord -d discord -c "SELECT count(*) FROM verification_requests;"
```

### Clean Up Old Records

```bash
# See database schema
docker-compose exec db psql -U discord -d discord -c "\d"

# Example: Remove verification requests older than 90 days
docker-compose exec db psql -U discord -d discord -c "
DELETE FROM verification_requests
WHERE created_at < now() - interval '90 days';
"
```

### Monitor Database Size

```bash
# PostgreSQL size
docker-compose exec db psql -U discord -d discord -c "
SELECT pg_size_pretty(pg_database_size('discord')) as size;
"

# Table sizes
docker-compose exec db psql -U discord -d discord -c "
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

## Common Issues

### "Token is invalid or expired"

The bot token you're using has been revoked or is incorrect:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Go to Bot → TOKEN
4. Click "Regenerate" to create a new token
5. Update your environment variable or config file
6. Restart the bot

### "Insufficient permissions"

The bot doesn't have required permissions in Discord:

1. Go to Server Settings → Roles → Find your bot role
2. Ensure these permissions are checked:
   - Send Messages
   - Embed Links
   - Manage Roles (if auto-naming)
   - Read Message History (if message handling)
3. Move bot role higher in the role hierarchy (above roles it needs to manage)

### "Invalid Discord object"

Could be guild ID, user ID, or role ID is incorrect or bot doesn't see it:

```bash
# Check bot can see the guild
docker-compose logs bot | grep "guild_id"

# Verify bot is in the guild
# Discord: Server Settings → Members → Look for your bot

# Check bot has necessary intents
# Discord Developer Portal → Settings → Bot → Intents
# Ensure: Server Members Intent, Message Content Intent (for text commands)
```

### "Connection reset by peer"

Discord API connection issue:

```bash
# Check if Discord is having issues
# Discord Status: https://discordstatus.com

# Restart bot to re-establish connection
docker-compose restart bot

# Check logs
docker-compose logs bot | tail -20
```

### "CSRF token invalid"

Web dashboard CSRF protection triggered:

1. Clear browser cookies
2. Reload the page
3. Log in again

If persistent:
- Verify `WEB__SECRET_KEY` hasn't changed
- Check clock synchronization (if using multiple servers)

---

## Escalation & Support

If you can't resolve an issue:

1. **Collect logs:**

```bash
docker-compose logs --tail=500 bot > error.log
docker-compose logs --tail=500 db >> error.log
```

2. **Create an issue** with:
   - Error logs (with sensitive info removed)
   - Configuration (without secrets)
   - Steps to reproduce
   - Docker version: `docker --version`

3. **Check documentation:**
   - [README.md](./README.md) - Features & quick start
   - [CONTRIBUTING.md](./CONTRIBUTING.md) - Development guide
   - [docs/CODEMAPS/](./docs/CODEMAPS/) - Architecture

## Development Utilities

### Available Scripts

Utility scripts in `/scripts` directory:

| Script | Purpose | Usage |
|--------|---------|-------|
| `run_tests.sh` | Run tests with coverage reporting | `./scripts/run_tests.sh [--no-coverage] [-v]` |
| `new_cog.py` | Scaffold a new cog with best practices | `python scripts/new_cog.py <cog_name>` |
| `update_dependencies.py` | Safely update dependency versions | `python scripts/update_dependencies.py` |
| `validate_cog_structure.py` | Validate cog directory structure | `python scripts/validate_cog_structure.py <cog_path>` |

---

**Last Updated:** 2026-04-24
**Version:** 1.0.2
