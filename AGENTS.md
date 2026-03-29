# Hablemos Discord Bot — Agent Instructions

## Project Overview

Spanish-language learning Discord bot built with discord.py 2.x. Prefix-based commands (`$`) and slash commands across multiple cogs. PostgreSQL via asyncpg, deployed on Railway via Docker. Python 3.12+. Linted with ruff.

## Architecture

```
hablemos.py          — Bot entrypoint, Hablemos(Bot) subclass
base_cog.py          — BaseCog base class (all cogs inherit from this)
config.py            — Centralized env config (Settings dataclass, get_int_env, etc.)
logger.py            — Logging setup (RotatingFileHandler + stdout)
ruff.toml            — Ruff linter configuration
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
- Use `%s`-style formatting in log calls, not f-strings (avoids interpolation when log level is disabled)
- Trailing newline at end of every file
- Import order: stdlib → third-party → local
- All code must pass `ruff check` before committing

### Error Handling
- Always bounds-check string/list indexing in parsers — the bot must never crash on user input
- Wrap Discord API calls (`fetch_message`, `get_channel`, etc.) in try/except with specific exceptions (`NotFound`, `Forbidden`, `HTTPException`)
- Use `BaseCog.cog_command_error` for cog-level error handling; don't silently swallow exceptions
- Never leak raw exception messages to users — show a friendly message and log the traceback server-side
- On hot paths (e.g., `on_message` listeners), suppress repeated errors to avoid log flooding

### Naming
- Cog directories: `<feature>_cog/`
- Cog classes: PascalCase (e.g., `QuoteGenerator`, `LanguageLeague`)
- Helper functions: snake_case
- Constants: UPPER_SNAKE_CASE
- Config values from env vars: use centralized helpers from `config.py` (`get_int_env`, `get_str_env`, `get_required_env`, `get_list_env`) — not raw `os.getenv()`

### Security
- No hardcoded tokens, secrets, or database URLs — always use environment variables
- No PII in log output
- Validate/sanitize all user-provided input before use

### Patterns to Follow
- New features → new cog directory under `cogs/` with `__init__.py`
- Cog-specific IDs and constants → `config.py` within the cog directory, using centralized env helpers with defaults
- Shared utilities → `cogs/utils/` (check for existing helpers before creating new ones)
- Admin commands → separate class in `admin.py`, loaded from `setup()`
- Admin command groups → use `@commands.group()` with subcommands (see `$league`, `$quoteadmin`, `$introtracker`, `$cog`)
- Cooldowns on user-facing commands to prevent spam
- Permission checks on admin/mod commands
- Real-time data tracking via `on_message` listeners with DB persistence (prefer over on-demand API scanning)
- Deduplicate shared logic into module-level helper functions or shared utilities
- Use `pathlib.Path` for file system operations — not `os.path` or `os.listdir`
- Slash command syncing is manual via `$sync` — never auto-sync in `on_ready`

### Patterns to Avoid
- Don't put business logic in `hablemos.py` — it's just the entrypoint
- Don't create global database connections — use `self.bot.db.pool`
- Don't use `discord.Client` — use `discord.ext.commands.Bot` (via `Hablemos` subclass)
- Don't hardcode guild/channel/role IDs in cog files — use `config.py` modules or database settings
- Don't duplicate utility classes across cogs — extract to `cogs/utils/`
- Don't define embed helpers locally in cog files — use `cogs/utils/embeds.py`
- Don't import from `typing` for types available as builtins (`list`, `dict`, `tuple`, `set`, `type | None`)
- Don't import `ParamSpec`/`TypeVar` when using Python 3.12 inline generic syntax (`def foo[T](x: T)`)
- Don't scan Discord message history for data that can be tracked incrementally via listeners
- Don't use f-strings in log calls
- Don't use in-memory caches for data that belongs in the database
- Don't use raw `pool.acquire()` + inline SQL in cog files — add query methods to DB mixins
- Don't call `tree.sync()` in `on_ready` — use the `$sync` owner command instead
