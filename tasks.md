# Refactoring Tasks

Tracked improvements identified during code review. Work through one at a time.

> **Effort ratings (1–5):** 1 = a few lines, done in minutes. 2 = small
> focused change, under 30 min. 3 = touches multiple files or needs some
> thought, ~1 hour. 4 = significant restructure across several files,
> needs testing. 5 = large cross-cutting change with migration or
> backwards-compatibility concerns.

## Pending

- [x] **Remove dead `ParamSpec`/`TypeVar` imports in league_cog** · effort: 1
  `cogs/league_cog/main.py` — Lines 11-12 import `ParamSpec` and `TypeVar` from
  `typing`, and lines 41-42 assign `P`/`T`, but line 44 uses the Python 3.12
  inline generic syntax `def handle_interaction_errors[**P, T]` which shadows
  them. The `typing` imports and module-level assignments are dead code.

- [x] **Use `pathlib.Path` for cog discovery instead of `os.listdir`/`os.path`** · effort: 1
  `hablemos.py` (`setup_hook`) and `cogs/admin_cog/main.py`
  (`_discover_extensions`) both use `os.listdir` + `os.path.isdir` for cog
  discovery. Replace with `pathlib.Path.glob()` or `iterdir()` for modern Python.
  Also deduplicate — both files have the same discovery logic.

- [x] **Use `pathlib.Path` in `convo_starter_help.py`** · effort: 1
  `cogs/convo_starter_cog/convo_starter_help.py` — Uses `os.path.dirname` chain
  to build file paths. Replace with `pathlib.Path(__file__).parent`.

- [x] **Add env var fallback for hardcoded IDs in `tickets_cog/config.py`** · effort: 1
  `cogs/tickets_cog/config.py` — `STAFF_FORUM_ID` and `ADMIN_FORUM_ID` are
  hardcoded without `get_int_env()` fallback, unlike other cog configs. Also
  missing type annotations.

- [x] **Add env var fallback for hardcoded IDs in `general_cog/main.py`** · effort: 1
  `cogs/general_cog/main.py` — `INVITE_LINK` contains a hardcoded client ID, and
  the `info` command has a hardcoded user mention `<@216848576549093376>`. Move
  these to config with env var fallback.

- [x] **Add env var fallback for hardcoded IDs in `league_cog/config.py`** · effort: 2
  `cogs/league_cog/config.py` — All guild/channel/role IDs are hardcoded `Final`
  constants without `get_int_env()` fallback. This makes it impossible to run the
  bot against a test server without code changes.

- [x] **Convert `$convo` to a slash/hybrid command** · effort: 4
  `cogs/conversation_cog/main.py` — Main user-facing feature is prefix-only with
  manual arg parsing. Convert to hybrid or slash command with `app_commands.choices`
  for language/level/category autocomplete.

- [x] **Replace f-strings in log calls with `%s`-style formatting** · effort: 4
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
