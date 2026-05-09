# Architecture

A map of the code. For conventions (style, patterns, what to avoid), see
[`../AGENTS.md`](../AGENTS.md).

## Stack

- **Python 3.12+** (`match`, inline generics, PEP 604 unions).
- **discord.py 2.x** (`discord.ext.commands.Bot`, slash commands, UI
  views, persistent views).
- **PostgreSQL via `asyncpg`** — one connection pool owned by the bot,
  accessed through the `Database` class at `self.bot.db`.
- **Railway** for hosting, `Dockerfile` for the container.
- **Ruff** for linting (`ruff.toml`).

## Top-level layout

```
hablemos.py          Bot entrypoint, subclasses discord.ext.commands.Bot
base_cog.py          BaseCog that every cog inherits from
config.py            Settings dataclass loaded from env vars
logger.py            Logging setup
ruff.toml            Ruff config
db/                  Database module (mixin-per-domain)
cogs/<feature>_cog/  One directory per feature, auto-discovered
cogs/utils/          Shared helpers (embeds, rate limiters, etc.)
scripts/             Utility scripts, ad-hoc tools
docs/                This folder
AGENTS.md            Agent contract (code style, patterns, git rules)
```

## Bot entrypoint — `hablemos.py`

- Defines `class Hablemos(Bot)`.
- `setup_hook` connects the DB (with retry), loads all auto-discovered
  extensions, and skips anything in the "disabled cogs" set stored in
  the database.
- `on_ready` resolves the configured online/error channels and posts an
  "I'm online" message.
- `on_command_completion` / `on_app_command_completion` record usage to
  `command_metrics` for the metrics rollup.

## Cog loading

Cogs are **auto-discovered** by `cogs/utils/discovery.py`: any
`cogs/*_cog/main.py` with a `setup(bot)` function is loaded at startup.
Secondary cog classes (admin splits, etc.) are explicitly added inside
that `setup()` — for example `league_cog/main.py` also loads
`LeagueAdminCog` from `admin.py`.

To disable a cog at runtime without redeploying, use the database-backed
disabled-cogs set (`$cog disable <name>`).

## Database layer — `db/`

One `Database` class composed of mixins, one mixin per domain:

```
db/
  __init__.py        Database class + DatabaseMixin base
  schema.py          initialize_schema() — all CREATE TABLE / migrations
  <domain>.py        Query methods for one domain
```

- `self.bot.db` is the shared `Database` instance.
- All queries use the connection pool via the `_fetch` / `_fetchrow` /
  `_fetchval` / `_execute` helpers on `DatabaseMixin`.
- New tables go in `schema.py`. New query methods go in the appropriate
  mixin.
- Adding a new domain: create `db/<domain>.py` with a mixin class, then
  add it to the `Database` inheritance list in `db/__init__.py`.

See [`database.md`](./database.md) for the table / mixin map.

## Configuration

- All env-driven values live in `config.py`'s `Settings` dataclass.
- Individual cogs may have their own `config.py` for cog-specific IDs
  and constants (e.g. `cogs/league_cog/config.py`).
- Never read `os.getenv` directly in a cog — use the helpers from the
  central `config.py` or a cog-local `config.py` module.

See [`deployment.md`](./deployment.md) for the full env var list.

## Interaction patterns

- **Slash commands** are registered per-guild (`guild_ids=[…]`) for
  instant sync when they're tied to a specific server; global commands
  sync manually via `$sync` (never in `on_ready`).
- **Persistent views** (buttons/selects that survive restarts) have
  `timeout=None`, stable `custom_id`s, and are registered once with
  `bot.add_view(...)`. Pattern: check `bot.persistent_views` to avoid
  stacking duplicates on cog reload.
- **On-message listeners** are used for incrementally-tracked state
  (league activity, crossword answers) rather than scanning history.

## Error handling

- `cogs/error_handler_cog/` posts command failures to a configured
  error channel.
- Cogs override `BaseCog.cog_command_error` for cog-level handling.
- Interaction callbacks use a decorator (`handle_interaction_errors` in
  `league_cog/main.py` and similar) to wrap ephemeral failure embeds.
- User-facing messages never leak raw exception strings; the traceback
  is logged server-side.

## What lives where — quick reference

| Concern | Location |
|---------|----------|
| New feature | New `cogs/<feature>_cog/` directory |
| Shared utility | `cogs/utils/` |
| Database table | `db/schema.py` + matching mixin |
| Env var | `config.py` Settings + `deployment.md` |
| Admin command | Separate class in the cog's `admin.py` |
| Persistent view | `views.py` inside the cog |
