# Contributing to Discord Bot

Thank you for your interest in contributing! This guide explains how to set up your development environment, run tests, and follow our code standards.

**Last Updated:** 2026-04-24

## Prerequisites

- **Python:** 3.12 or higher
- **Git:** For version control
- **Virtual Environment:** Python's built-in `venv` module

## Initial Setup

### 1. Clone and Install

```bash
# Clone the repository
git clone https://github.com/xurxogr/discord-bot.git
cd discord-bot

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### 2. Configure Credentials

The bot requires a Discord token. Choose one setup method:

**Option A: Environment Variables (Recommended for development)**

```bash
export BOT__TOKEN="your_discord_bot_token"
```

**Option B: JSON Configuration File**

```bash
mkdir -p ~/.config/discord-bot
cp docs/config/config.example.json ~/.config/discord-bot/config.json
# Edit ~/.config/discord-bot/config.json and add your token
```

### 3. Initialize Database

```bash
# Run migrations (creates SQLite database by default)
alembic upgrade head

# Or if using PostgreSQL:
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/discord"
alembic upgrade head
```

## Development Workflow

### Available Scripts

Utility scripts in `/scripts` directory:

| Script | Purpose | Usage |
|--------|---------|-------|
| `run_tests.sh` | Run tests with coverage reporting | `./scripts/run_tests.sh [--no-coverage] [-v]` |
| `new_cog.py` | Scaffold a new cog with best practices | `python scripts/new_cog.py <cog_name>` |
| `update_dependencies.py` | Safely update dependency versions | `python scripts/update_dependencies.py` |
| `validate_cog_structure.py` | Validate cog directory structure | `python scripts/validate_cog_structure.py <cog_path>` |

### Running Tests

Tests are run using pytest with coverage reporting enabled by default (98%+ coverage required).

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/verification/test_service.py

# Run tests matching a pattern
pytest -k "test_verification"

# Run without coverage (faster)
pytest --no-cov

# Generate HTML coverage report
pytest --cov-report=html
# Open htmlcov/index.html to view results
```

**Using the test runner script:**

```bash
# Run all tests with HTML coverage report
./scripts/run_tests.sh

# Run without coverage
./scripts/run_tests.sh --no-coverage

# Run specific test directory
./scripts/run_tests.sh --test tests/verification

# Run with verbose output
./scripts/run_tests.sh -v
```

### Code Quality Checks

All code must pass linting, formatting, and type checking:

```bash
# Lint code (includes security and async checks)
ruff check discord_bot/

# Format code
ruff format discord_bot/

# Type checking
mypy discord_bot/

# Check for dead code
vulture discord_bot/

# Security audit of dependencies
pip-audit
```

### Running the Bot Locally

```bash
# With environment variable token
export BOT__TOKEN="your_token"
export WEB__ENABLED="true"
export WEB__SECRET_KEY="dev-secret-key"
export WEB__CLIENT_ID="your_client_id"
export WEB__CLIENT_SECRET="your_client_secret"

# Run the bot
discord-bot

# Or with specific config file
discord-bot --config ~/.config/discord-bot/config.json
```

The web dashboard will be available at `http://localhost:8000` if enabled.

## Code Standards

<!-- AUTO-GENERATED: Code standards from .claude/rules/common/coding-style.md -->

### Immutability (CRITICAL)

ALWAYS create new objects, NEVER mutate existing ones:

```python
# WRONG: Mutates existing dict
def update_guild_config(config, setting, value):
    config[setting] = value
    return config

# CORRECT: Returns new dict with change
def update_guild_config(config, setting, value):
    return {**config, setting: value}
```

Rationale: Prevents hidden side effects, makes debugging easier, enables safe concurrency.

### File Organization

- **High cohesion, low coupling** over large monolithic files
- **Typical file size:** 200-400 lines, maximum 800 lines
- **Extract utilities** from large modules
- **Organize by feature/domain**, not by type

### Error Handling

- Handle errors explicitly at every level
- Provide user-friendly messages in UI-facing code
- Log detailed context on the server side
- Never silently swallow errors

### Input Validation

- Validate ALL user input before processing
- Use Pydantic schemas for API requests
- Fail fast with clear error messages
- Never trust external data (API responses, file content)

### Import Ordering (CRITICAL)

ALWAYS place imports at the top of the file, NEVER inside methods:

```python
# WRONG: Import inside method
def get_config():
    from discord_bot.config import Config  # Don't do this!
    return Config()

# CORRECT: Import at top of file
from discord_bot.config import Config

def get_config():
    return Config()
```

Rationale: Ensures imports happen once during module load, enables static analysis, prevents circular dependencies at runtime.

### Code Quality Checklist

Before marking work complete:
- [ ] Code is readable and well-named
- [ ] Functions are small (<50 lines)
- [ ] Files are focused (<800 lines)
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling
- [ ] No hardcoded values (use constants or config)
- [ ] No mutation (immutable patterns used)

<!-- END AUTO-GENERATED -->

## Testing Requirements

### Minimum Coverage: 98%

Test your changes thoroughly:

1. **Unit Tests** - Individual functions, utilities, schemas
2. **Integration Tests** - Service methods, database operations
3. **E2E Tests** - Critical Discord bot flows (when applicable)

### Test-Driven Development (TDD)

Follow this workflow for new features:

1. **RED** - Write test first, it should FAIL
2. **GREEN** - Write minimal implementation to PASS
3. **IMPROVE** - Refactor while keeping tests passing
4. **VERIFY** - Ensure 80%+ coverage

Example:

```python
# tests/verification/test_verification_service.py
@pytest.mark.asyncio
async def test_create_verification_request_stores_user_id(db_session):
    service = VerificationService(db_session)

    # RED: Test fails because method doesn't exist yet
    request = await service.create_verification_request(
        guild_id=123456789,
        user_id=987654321,
    )

    # GREEN: Implement to pass
    assert request.user_id == 987654321
    assert request.guild_id == 123456789
```

## Project Structure

<!-- AUTO-GENERATED: From docs/CODEMAPS/INDEX.md -->

```
discord_bot/
├── __main__.py                 # Entry point (async launcher)
├── bot.py                      # DiscordBot class, cog loading
├── common/                     # Shared infrastructure
│   ├── core/                   # Settings, logging, app configuration
│   ├── models/                 # SQLAlchemy ORM models
│   ├── services/               # Database, config, event bus
│   ├── schemas/                # Pydantic schemas for validation
│   ├── enums/                  # Event types, config option types
│   └── utils/                  # Utilities (message handling)
├── verification/               # Verification module (cog + service)
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

<!-- END AUTO-GENERATED -->

## Architecture Patterns

### Cogs (Discord Event Handlers)

- **Thin wrappers** around Discord events
- Delegate business logic to services
- Handle I/O and user communication only

Example:

```python
# discord_bot/verification/cog.py
@discord.app_commands.command(name="verify")
async def verify(self, interaction: discord.Interaction) -> None:
    """Handle /verify command."""
    try:
        # Thin: Just coordinate service calls
        verification = await self.service.create_verification_request(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )
        await interaction.response.send_message(
            f"Verification request created: {verification.id}"
        )
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        await interaction.response.send_message("Verification failed", ephemeral=True)
```

### Services (Business Logic)

- Pure business logic, no Discord dependencies
- Encapsulate database access
- Testable with mocks

Example:

```python
# discord_bot/verification/service.py
class VerificationService:
    async def create_verification_request(
        self, guild_id: int, user_id: int
    ) -> VerificationRequest:
        request = VerificationRequest(
            guild_id=guild_id,
            user_id=user_id,
            status=VerificationStatus.PENDING,
        )
        async with self.db.session() as session:
            session.add(request)
            await session.commit()
        return request
```

### Schemas (Validation)

Use Pydantic for request/response validation:

```python
# discord_bot/common/schemas/verification.py
class VerificationRequestSchema(BaseModel):
    guild_id: int
    user_id: int
    status: VerificationStatus = VerificationStatus.PENDING

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode
    )
```

## Creating a New Cog

Use the script to generate a new cog structure:

```bash
python scripts/new_cog.py MyFeature
```

This creates:

```
discord_bot/myfeature/
├── __init__.py
├── cog.py                  # Discord event handler
├── service.py              # Business logic
├── models.py               # ORM models
├── config.py               # Pydantic config schema
└── formatters.py           # Embed builders

tests/myfeature/
├── __init__.py
├── test_cog.py
└── test_service.py
```

## Database Migrations

Using Alembic for schema changes:

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new_field to users"

# Review the migration in migrations/versions/
# Then apply it:
alembic upgrade head

# Rollback if needed:
alembic downgrade -1
```

## Pre-commit Hooks

The project includes pre-commit configuration to automatically check code quality:

```bash
# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Run on staged files (happens automatically on commit)
git commit -m "Your message"
```

## Making a Pull Request

1. **Create a feature branch:**

```bash
git checkout -b feature/my-feature
```

2. **Make your changes**, ensuring:
   - Tests pass: `pytest`
   - Code passes linting: `ruff check discord_bot/`
   - Type checks: `mypy discord_bot/`

3. **Commit with clear messages:**

```bash
git commit -m "feat: add verification user limit

- Add user_limit field to VerificationConfig
- Enforce limit in verify command
- Add tests for limit enforcement

Fixes #123"
```

4. **Push and create PR:**

```bash
git push -u origin feature/my-feature
```

5. **PR checklist:**
   - [ ] All tests pass
   - [ ] Coverage >= 80%
   - [ ] No linting errors
   - [ ] Type checking passes
   - [ ] Codemaps updated (if architecture changed)

## Common Issues

### Virtual Environment Not Activated

```bash
source venv/bin/activate
# On Windows: venv\Scripts\activate
```

### Tests Fail on Import

Make sure you installed in editable mode:

```bash
pip install -e ".[dev]"
```

### Database Lock (SQLite)

SQLite can timeout with concurrent writes. The project includes retry logic. If you hit this during testing:

```bash
# Use PostgreSQL for development
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost/discord"
alembic upgrade head
pytest
```

### Type Checking Errors

Common fixes:

```python
# Add type annotations
def get_user(user_id: int) -> discord.User:
    ...

# Use TYPE_CHECKING for forward references
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from discord_bot.verification.service import VerificationService

# Import from typing for 3.12+
from typing import Optional
config: Optional[dict] = None
```

## Getting Help

- **Issues:** Check GitHub issues for similar problems
- **Discussions:** Use GitHub discussions for questions
- **Code Review:** Ask in PR comments for help understanding code

## Security

Before submitting a PR:

- [ ] No hardcoded secrets (tokens, keys, passwords)
- [ ] All user inputs validated
- [ ] SQL injection prevention (using SQLAlchemy parameterization)
- [ ] XSS prevention (Jinja2 auto-escapes by default)
- [ ] No sensitive data in error messages
- [ ] Rate limiting enabled on endpoints

See [.claude/rules/common/security.md](.claude/rules/common/security.md) for detailed security guidelines.

## Questions?

Feel free to:
- Open an issue with the `question` label
- Check existing documentation in `/docs`
- Review code comments and docstrings

Happy coding!
