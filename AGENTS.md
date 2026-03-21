# Hablemos Discord Bot — Agent Instructions

## Project Overview

Spanish-language learning Discord bot built with discord.py 2.x. Prefix-based commands (`$`), some slash commands for the league system. PostgreSQL via asyncpg, deployed on Railway via Docker. Python 3.12+.

## Architecture

```
hablemos.py          — Bot entrypoint, Hablemos(Bot) subclass
base_cog.py          — BaseCog base class (all cogs inherit from this)
logger.py            — Logging setup (RotatingFileHandler + stdout)
db/                  — Database module
  __init__.py        — Database class (composes mixins), DatabaseMixin base
  schema.py          — initialize_schema() — all CREATE TABLE / migrations
  <domain>.py        — One mixin per domain (notes, leaderboard, practice, etc.)
cogs/<name>_cog/     — Each feature is a cog in its own directory
  __init__.py        — Empty (required for package imports)
  main.py            — Cog class + setup(bot) function (auto-loaded)
  admin.py           — Optional admin commands (loaded from main.py's setup)
  config.py          — Optional cog-specific configuration (IDs, constants)
  *.py               — Helpers, parsers, etc.
cogs/utils/          — Shared utilities
  embeds.py          — Reusable embed helpers (green_embed, red_embed, etc.)
  rate_limiter.py    — Shared RateLimiter for API calls
```

### Cog Loading

Cogs are auto-discovered: any `cogs/*_cog/main.py` is loaded at startup. Additional cog classes (like admin cogs) must be explicitly loaded in the `setup()` function of `main.py`.

### Database Access

Always use `self.bot.db` (the shared `Database` instance). All queries go through the asyncpg connection pool. New query methods go in the appropriate mixin under `db/`. New tables go in `db/schema.py`. The `Database` class in `db/__init__.py` composes all mixins — add new mixins to its inheritance list.

## Code Standards

### Style
- Python 3.12+ — use builtin generics (`list[dict]`, `str | None`) not `typing.List`, `typing.Optional`, etc.
- Type hints on all function signatures
- Docstrings on public functions and classes (module-level docstring for cog files)
- Use `logging.getLogger(__name__)` per module — never `print()` or bare `logging.info()` for operational output
- Trailing newline at end of every file
- Import order: stdlib → third-party → local

### Error Handling
- Always bounds-check string/list indexing in parsers — the bot must never crash on user input
- Wrap Discord API calls (`fetch_message`, `get_channel`, etc.) in try/except
- Use `BaseCog.cog_command_error` for cog-level error handling; don't silently swallow exceptions

### Naming
- Cog directories: `<feature>_cog/`
- Cog classes: PascalCase (e.g., `QuoteGenerator`, `LanguageLeague`)
- Helper functions: snake_case
- Constants: UPPER_SNAKE_CASE
- Config values from env vars: access via `os.getenv()` with sensible defaults

### Security
- No hardcoded tokens, secrets, or database URLs — always use environment variables
- No PII in log output
- Validate/sanitize all user-provided input before use

### Patterns to Follow
- New features → new cog directory under `cogs/` with `__init__.py`
- Cog-specific IDs and constants → `config.py` within the cog directory, loaded from env vars with defaults
- Shared utilities → `cogs/utils/` (check for existing helpers before creating new ones)
- Admin commands → separate class in `admin.py`, loaded from `setup()`
- Cooldowns on user-facing commands to prevent spam
- Permission checks on admin/mod commands

### Patterns to Avoid
- Don't put business logic in `hablemos.py` — it's just the entrypoint
- Don't create global database connections — use `self.bot.db.pool`
- Don't use `discord.Client` — use `discord.ext.commands.Bot` (via `Hablemos` subclass)
- Don't hardcode guild/channel/role IDs in cog files — use `config.py` modules or database settings
- Don't duplicate utility classes across cogs — extract to `cogs/utils/`
- Don't define embed helpers locally in cog files — use `cogs/utils/embeds.py`
- Don't import from `typing` for types available as builtins (`list`, `dict`, `tuple`, `set`, `type | None`)
