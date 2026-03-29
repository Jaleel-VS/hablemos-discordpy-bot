# Refactoring Tasks

Tracked improvements identified during code review. Work through one at a time.

> **Effort ratings (1–5):** 1 = a few lines, done in minutes. 2 = small
> focused change, under 30 min. 3 = touches multiple files or needs some
> thought, ~1 hour. 4 = significant restructure across several files,
> needs testing. 5 = large cross-cutting change with migration or
> backwards-compatibility concerns.

## Pending

- [ ] **Replace `asyncio.get_event_loop().time()`** · effort: 1
  `cogs/conversation_cog/main.py` — Deprecated in Python 3.12+. Replace with
  `time.monotonic()`.

- [ ] **Move inline SQL into DB mixins** · effort: 2
  `cogs/conversation_cog/main.py` (`conversation_stats`) and
  `cogs/league_cog/admin.py` (`_handle_audit`) use raw `pool.acquire()` with
  inline SQL. Move these queries into the appropriate DB mixin methods.

- [ ] **Stop syncing slash commands on every `on_ready`** · effort: 2
  `hablemos.py` — `tree.sync()` on every restart hits rate limits. Move to an
  owner-only `$sync` command that's run manually when commands change.

- [ ] **Narrow `Intents.all()` to only what's needed** · effort: 2
  `hablemos.py` — Explicitly declare required intents (members, message_content,
  presences, etc.) instead of requesting all. Documents actual needs and is more
  secure.

- [ ] **Extract error handler from `hablemos.py`** · effort: 3
  The `on_command_error` handler has a 30-item quotes list and mixed
  responsibilities (logging, metrics, user messages). Extract the quotes to a
  constant and consider moving error handling to a utility or dedicated cog.

- [ ] **Convert `$league` admin to `@commands.group()` subcommands** · effort: 3
  `cogs/league_cog/admin.py` — Replace the manual `if/elif` dispatcher in
  `league_admin` with proper `@commands.group()` subcommands like `$introtracker`
  and `$quoteadmin` already use. Gets free per-subcommand help, argument parsing,
  and error handling.

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
- [x] **Auto-generate `/help` from cog metadata** — `cogs/general_cog/main.py`
- [x] **Fix cog docstrings for user-facing help** — 12 cog files
