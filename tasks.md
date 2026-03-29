# Refactoring Tasks

Tracked improvements identified during code review. Work through one at a time.

> **Effort ratings (1–5):** 1 = a few lines, done in minutes. 2 = small
> focused change, under 30 min. 3 = touches multiple files or needs some
> thought, ~1 hour. 4 = significant restructure across several files,
> needs testing. 5 = large cross-cutting change with migration or
> backwards-compatibility concerns.

## Pending

- [ ] **Convert `$convo` to a slash/hybrid command** · effort: 4
  `cogs/conversation_cog/main.py` — Main user-facing feature is prefix-only with
  manual arg parsing. Convert to hybrid or slash command with `app_commands.choices`
  for language/level/category autocomplete.

- [ ] **Replace f-strings in log calls with `%s`-style formatting** · effort: 4
  31 files use `logger.xxx(f"...")` instead of `logger.xxx("...", arg)`. This
  violates the project code standard — f-strings are interpolated even when the
  log level is disabled, wasting CPU. Sweep all files under `cogs/`, `db/`, and
  root modules.

## Done

- [x] **Fix `Hangman` inheriting from `Cog`** — `cogs/hangman_cog/hangman.py`
- [x] **Replace `asyncio.get_event_loop().time()`** — `cogs/conversation_cog/main.py`
- [x] **Move inline SQL into DB mixins** — `db/conversations.py`, `db/leaderboard.py`
- [x] **Stop syncing slash commands on every `on_ready`** — `hablemos.py`, `cogs/admin_cog/main.py`
- [x] **Narrow `Intents.all()` to only what's needed** — `hablemos.py`
- [x] **Extract error handler from `hablemos.py`** — `cogs/error_handler_cog/main.py`
- [x] **Convert `$league` admin to `@commands.group()` subcommands** — `cogs/league_cog/admin.py`
- [x] **Auto-generate `/help` from cog metadata** — `cogs/general_cog/main.py`
- [x] **Fix cog docstrings for user-facing help** — 12 cog files
