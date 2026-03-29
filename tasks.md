# Refactoring Tasks

Tracked improvements identified during code review. Work through one at a time.

> **Effort ratings (1–5):** 1 = a few lines, done in minutes. 2 = small
> focused change, under 30 min. 3 = touches multiple files or needs some
> thought, ~1 hour. 4 = significant restructure across several files,
> needs testing. 5 = large cross-cutting change with migration or
> backwards-compatibility concerns.

## Pending

- [ ] **Stop leaking raw exception messages to users** — effort 2 — `cogs/league_cog/main.py:52,569,607,777,879`, `cogs/vocab_cog/main.py:94,181,241,282,359`, `cogs/database_cog/main.py:39,66,102,124`, `cogs/website_manager_cog/views.py:91,135,327,339,381`, `cogs/website_manager_cog/modals.py:91,201,311`, `cogs/ask_cog/main.py:198`, `cogs/admin_cog/main.py:184`
  AGENTS.md says "Never leak raw exception messages to users — show a friendly message and log the traceback server-side." Many error handlers embed `{e!s}` or `{e}` directly in user-facing messages. Replace with generic messages and ensure the traceback is logged.

- [ ] **Add cooldowns to user-facing commands that lack them** — effort 2 — `cogs/hangman_cog/main.py:38` (`$hangman`), `cogs/convo_starter_cog/main.py:35` (`$topic`), `cogs/conjugation_cog/main.py:63` (`$conj`), `cogs/spotify_cog/main.py:16` (`$nowplaying`), `cogs/database_cog/main.py` (`$note`, `$shownote`, `$notes`, `$deletenote`)
  AGENTS.md requires cooldowns on user-facing commands to prevent spam. Several public commands have no `@commands.cooldown` decorator. (Database commands are owner-only so lower priority, but hangman/topic/conj/nowplaying are public.)

- [ ] **Add `on_timeout` handlers to all persistent Views** — effort 2 — `cogs/website_manager_cog/views.py` (all 7 View classes), `cogs/practice_cog/views.py` (`PracticeView`, `QualityRatingView`)
  When a View times out, its buttons/selects become unresponsive but still appear clickable. Each View should implement `on_timeout` to disable components or edit the message, preventing user confusion.

- [ ] **Add `interaction_check` to website manager Views** — effort 2 — `cogs/website_manager_cog/views.py` (all View classes)
  None of the website manager Views implement `interaction_check`, meaning any user could click another user's management buttons. Each View should verify `interaction.user` matches the original invoker.

- [ ] **Deduplicate `_show_question` and `_show_next_question` in practice cog** — effort 2 — `cogs/practice_cog/main.py:226-260,410-450`
  These two methods are nearly identical (same card mode logic, same distractor fetching, same view creation). The only difference is the `show_disclaimer` flag. Extract into a single method with a `show_disclaimer` parameter.

- [ ] **Deduplicate leaderboard image cleanup pattern** — effort 1 — `cogs/league_cog/main.py:770`
  `Path(image_path).unlink(missing_ok=True)` is correct but the temp file creation at line ~760 uses `generate_leaderboard_image` which returns a path string. Consider using `tempfile.NamedTemporaryFile` consistently (like quote_generator does) or wrapping in a try/finally to guarantee cleanup on all error paths.

- [ ] **Move `SummaryCache` to database or add bounded eviction** — effort 3 — `cogs/summary_cog/cache.py`
  `SummaryCache` is an unbounded in-memory dict. AGENTS.md says "Don't use in-memory caches for data that belongs in the database." While summaries are ephemeral, the cache has no max-size eviction — a busy server could accumulate entries until TTL expires. Either add a max-size cap with LRU eviction, or move to DB-backed caching.

- [ ] **Move `active_sessions` dict in practice cog to a bounded structure** — effort 2 — `cogs/practice_cog/main.py:34`
  `self.active_sessions: dict[int, PracticeSession]` is unbounded in-memory state. If a user starts a session and never finishes (e.g., bot restarts, user leaves), the entry persists until cog reload. Add a TTL or max-size, and clean up stale sessions periodically.

- [ ] **Add `try/except` for Discord API calls in `_announce_round_winners`** — effort 1 — `cogs/league_cog/main.py:330-345`
  `channel.send(message)` is wrapped in a broad `except Exception`, but `self.bot.get_channel()` returning `None` is handled — good. However, the `channel.send()` should specifically catch `Forbidden`/`HTTPException` for clearer error handling per AGENTS.md.

- [ ] **Add `try/except` for `channel.fetch_message` in `league_admin.py` `validatemessage`** — effort 1 — `cogs/league_cog/admin.py:195`
  `await channel.fetch_message(message_id)` is inside a broad `try/except` but should specifically catch `NotFound`/`Forbidden`/`HTTPException` before the generic `Exception` (which it does at lines 230-234, but the fetch is at 195 inside the same broad block — the specific catches are correct but the structure could be tighter).

- [ ] **Add `cog_command_error` to cogs that override `BaseCog` error handling inconsistently** — effort 2 — `cogs/hangman_cog/main.py`, `cogs/convo_starter_cog/main.py`, `cogs/database_cog/main.py`, `cogs/relay_cog/main.py`, `cogs/conjugation_cog/main.py`
  Several cogs don't override `cog_command_error` at all, falling through to `BaseCog`'s handler which only handles `CommandOnCooldown`. Others (practice, conversation, summary) have their own handlers. Cogs with `MissingPermissions` checks or other expected errors should handle them locally to give contextual messages.

- [ ] **Use `Hablemos` type in cog `__init__` signatures instead of `commands.Bot`** — effort 2 — `cogs/league_cog/main.py:68`, `cogs/practice_cog/main.py:30`, `cogs/admin_cog/main.py:28`, `cogs/vocab_cog/main.py:82`, `cogs/relay_cog/main.py:13`, `cogs/ask_cog/main.py:148`
  Multiple cogs type-hint `bot` as `commands.Bot` in their `__init__`. Since the bot is always a `Hablemos` instance, this hides `.db` and `.settings` from type checkers. Use a `TYPE_CHECKING` guard to import `Hablemos` and annotate correctly.

- [ ] **Clean up `Hangman` class — missing type hints on most methods** — effort 3 — `cogs/hangman_cog/hangman.py`
  The `Hangman` class has no type hints on `game_loop`, `game_in_progress`, `create_dict_indices`, `get_user_guess`, `get_input_info`, `update_single_letter`, `replace_hidden_character`, `send_embed`, `extend_found_set`, `send_final_embed`, `word_found`, `max_errors_reached`. AGENTS.md requires type hints on all function signatures.

- [ ] **Add return type annotations to `db/` mixin methods** — effort 3 — `db/leaderboard.py`, `db/schema.py`, `db/notes.py`, `db/quotes.py`, `db/settings.py`, `db/vocab.py`, `db/practice.py`, `db/conversations.py`
  Many DB mixin methods have parameter type hints but are missing return type annotations (e.g., `-> bool`, `-> int`, `-> dict | None`). Some methods like `leaderboard_join`, `exclude_channel`, `quote_ban_user` always return `True` — their return types should be explicit.

- [ ] **Extract shared "resolve user from mention or ID" helper** — effort 2 — `cogs/quote_generator_cog/admin.py:22-29` (`_resolve_user_id`), `cogs/league_cog/admin.py:52-53,72-73`
  Both quote admin and league admin have inline logic to resolve a user ID from mentions or raw input. The quote admin has a proper helper function; league admin does it inline. Extract to `cogs/utils/` and reuse.

- [ ] **Replace `dict` return types with `TypedDict` or dataclasses in DB mixins** — effort 4 — `db/leaderboard.py`, `db/conversations.py`, `db/metrics.py`
  Methods like `get_user_stats`, `get_leaderboard`, `get_metrics_summary` return plain `dict` with implicit key contracts. Using `TypedDict` or dataclasses would make the API self-documenting and catch key typos at type-check time.

- [ ] **Add `View.on_timeout` to `VisibilityView` in ask cog** — effort 1 — `cogs/ask_cog/main.py:93-101`
  `VisibilityView.on_timeout` tries to edit `self.message`, but `self.message` is set after the view is sent. If the assignment fails (e.g., `edit` returns `None`), `self.message` may be the processing message, not the view message. The logic is fragile — verify `self.message` is always correctly set.

## Done

- [x] **Remove `from __future__ import annotations` (unnecessary in 3.12+)** — `config.py`, `cogs/practice_cog/modals.py`, `cogs/practice_cog/views.py`
- [x] **Replace f-strings in `relay_cog` log calls with `%s`-style** — `cogs/relay_cog/main.py`
- [x] **Replace f-string in `league_cog` `_warm_caches` log call** — `cogs/league_cog/main.py`
- [x] **Replace `os.path.exists` / `os.remove` with `pathlib.Path` in quote generator** — `cogs/quote_generator_cog/main.py`
- [x] **Replace `os.path` / `os.walk` with `pathlib` in `hangman_help.py`** — `cogs/hangman_cog/hangman_help.py`
- [x] **Add module-level docstrings to files that lack them** — 18 files
- [x] **Type `self.bot` as `Hablemos` instead of `Bot` in `BaseCog`** — `base_cog.py`
- [x] **Guard `handle_interaction_errors` decorator against leaking exception text** — `cogs/league_cog/main.py`
- [x] **Replace `open()` with `pathlib.Path` for CSV loading in hangman** — `cogs/hangman_cog/hangman_help.py`
- [x] **Remove `DatabaseCommands` `!` prefix references in docstrings** — `cogs/database_cog/main.py`
- [x] **Guard `error_handler_cog` against DM context** — `cogs/error_handler_cog/main.py`
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
