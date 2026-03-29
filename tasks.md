# Refactoring Tasks

Tracked improvements identified during code review. Work through one at a time.

> **Effort ratings (1–5):** 1 = a few lines, done in minutes. 2 = small
> focused change, under 30 min. 3 = touches multiple files or needs some
> thought, ~1 hour. 4 = significant restructure across several files,
> needs testing. 5 = large cross-cutting change with migration or
> backwards-compatibility concerns.

## Pending

*No pending tasks.*

## Done

- [x] **Replace f-strings in log calls with `%s`-style formatting** — 30 files
- [x] **Convert `$convo` to a slash/hybrid command** — `cogs/conversation_cog/main.py`
- [x] **Add env var fallback for hardcoded IDs in `league_cog/config.py`** — `cogs/league_cog/config.py`
- [x] **Add env var fallback for hardcoded IDs in `general_cog/main.py`** — `cogs/general_cog/main.py`, `cogs/general_cog/config.py`
- [x] **Add env var fallback for hardcoded IDs in `tickets_cog/config.py`** — `cogs/tickets_cog/config.py`
- [x] **Use `pathlib.Path` in `convo_starter_help.py`** — `cogs/convo_starter_cog/convo_starter_help.py`
- [x] **Use `pathlib.Path` for cog discovery instead of `os.listdir`/`os.path`** — `hablemos.py`, `cogs/admin_cog/main.py`, `cogs/utils/discovery.py`
- [x] **Remove dead `ParamSpec`/`TypeVar` imports in league_cog** — `cogs/league_cog/main.py`
- [x] **Fix cog docstrings for user-facing help** — 12 cog files
- [x] **Auto-generate `/help` from cog metadata** — `cogs/general_cog/main.py`
- [x] **Convert `$league` admin to `@commands.group()` subcommands** — `cogs/league_cog/admin.py`
- [x] **Extract error handler from `hablemos.py`** — `cogs/error_handler_cog/main.py`
- [x] **Narrow `Intents.all()` to only what's needed** — `hablemos.py`
- [x] **Stop syncing slash commands on every `on_ready`** — `hablemos.py`, `cogs/admin_cog/main.py`
- [x] **Move inline SQL into DB mixins** — `db/conversations.py`, `db/leaderboard.py`
- [x] **Replace `asyncio.get_event_loop().time()`** — `cogs/conversation_cog/main.py`
- [x] **Fix `Hangman` inheriting from `Cog`** — `cogs/hangman_cog/hangman.py`
