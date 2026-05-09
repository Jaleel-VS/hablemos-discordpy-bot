# Crossword (`crossword_cog`)

Mini crossword puzzles for language practice in Spanish or English.

## Overview

The crossword cog generates small (4–6 word) crossword puzzles on the
fly, with all clues and answers in the player's chosen practice language.
Players answer by typing words in the channel; the bot checks answers,
updates the grid, and awards points for completion. Games run in-channel
with a 10-minute timeout.

Key features:

- **Two difficulties**: Beginner (30% of letters pre-revealed) and
  Advanced (clean grid).
- **Two languages**: Spanish (🇪🇸) and English (🇬🇧) — both clues and
  answers are in the selected language.
- **Grid generation**: Backtracking algorithm places words so they
  intersect at shared letters. First word horizontal at center,
  subsequent words alternate direction. See `grid.py` for details.
- **Leaderboard**: Per-server leaderboard tracks games completed,
  timeouts, quits, hints used, and solve times.
- **Metrics**: New schema (added May 2025) records per-game, per-player,
  and per-word-event data for rich analytics. Legacy `crossword_scores`
  table no longer written to.
- **Interrupt recovery**: If the bot restarts mid-game, players are
  notified on the next boot and the game state is cleared.

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$crossword [difficulty] [language]` / `$cw` | Start a new crossword. Args: `beginner`/`advanced`, `es`/`en`/`spanish`/`english`. Defaults: beginner, Spanish. | None | 10s/channel |
| `/crossword` | Slash version with dropdowns for difficulty and language. | None | 10s/channel |
| `$cwl` / `$cwleaderboard [scope]` | Per-server crossword leaderboard. Scopes: `all` (default), `week`, `month`, or `<N>` days. Shows top 10 users with completion metrics. | None | None |
| In-game: `quit` | Cancel the game (starter or users with manage-messages permission). | Starter or manage-messages | None |
| In-game: `giveup` / `reveal` | End the game and show all answers (starter only). | Starter | None |
| In-game: `!hint` | Reveal one random letter (max 2 per game). | None | None |

### Admin commands

Owner-only. Defined directly in `main.py`.

| Command | Description |
|---------|-------------|
| `$cwtimeout <seconds>` | Override the crossword timeout for the remaining bot process lifetime. Useful for testing. |
| `$cwstats [days\|all]` | Aggregate crossword stats: games, participants, completion breakdown (completed/timeout/quit/interrupted), hints usage, top solvers. |
| `$cwwords <hardest\|easiest\|unseen> [lang] [limit]` | Per-word solve-rate analysis. `unseen` requires a language; others filter optionally. Displays word, solve rate, times seen, avg solve time. |

## Listeners & flows

### `on_message` → answer checking

Every message in a channel with an active game is checked:

1. **Ignore conditions**: bot message, DM, no active game, timeout
   watcher cancelled.
2. **Special commands**: `quit`, `giveup`/`reveal`, `!hint`.
3. **Answer matching**: Normalize message text (strip accents, lowercase,
   keep only alphanumerics) and compare against unsolved words.
4. If match:
   - Mark word as solved, record solver, solve time, hint flag.
   - Re-render grid with new revealed cells.
   - Update game message (embed + image, or Components V2 view).
   - If all words solved, end game with completion metrics.

### Timeout watcher

A per-game `asyncio.Task` sleeps for `GAME_TIMEOUT_SECONDS` (600s by
default). On wake:

1. End the game with `completion="timeout"`.
2. Post a timeout embed with final grid and revealed answers.
3. Record game and participant data to DB.
4. Clear `crossword_active_games` row.

If the game ends early (all solved, quit, or reveal), the watcher is
cancelled.

### Interrupt recovery (on cog load)

On bot restart:

1. Fetch all rows from `crossword_active_games`.
2. For each row, resolve the channel (guild, thread, or DM).
3. Post a "game interrupted" message with context.
4. Delete the row.

Best-effort: failures per row are logged but don't stop processing of
others.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `crossword_words` | `CrosswordMixin` | The word pool. Columns: `word_es`, `word_en`, `clue_es`, `clue_en`, `difficulty`, `theme`. |
| `crossword_scores` | `CrosswordMixin` | **Legacy flat-scores table. No longer written to.** Retained for historical reference. |
| `crossword_active_games` | `CrosswordMixin` | One row per in-flight game (PK `channel_id`). Carries `game_id` for recovery. Cleared when game ends or is interrupted. |
| `crossword_games` | `CrosswordMixin` | One row per completed/ended game. Columns: `game_id`, `guild_id`, `channel_id`, `starter_id`, `difficulty`, `language`, `word_count`, `completion` ∈ {`completed`, `timeout`, `quit`, `interrupted`}, `hints_used`, `started_at`, `ended_at`, `elapsed_seconds`. |
| `crossword_participants` | `CrosswordMixin` | `(game_id, user_id)` with `words_solved`, `is_starter`. Starter always present even at 0 solved. |
| `crossword_word_events` | `CrosswordMixin` | Per-word solve data: `game_id`, `word`, `solved`, `solved_by`, `seconds_to_solve`, `had_hint`. Drives `$cwwords` analysis. |

Migration note: When the new metrics schema landed (May 2025), writes to
`crossword_scores` stopped but the table remains for historical queries.
`$cwstats` and `$cwleaderboard` read only the new tables.

See [`../database.md`](../database.md) for query methods (all in
`CrosswordMixin`).

## Configuration & environment variables

| Constant | Location | Default | Purpose |
|---------  |----------|---------|---------|
| `GAME_TIMEOUT_SECONDS` | `cogs/crossword_cog/config.py` | 600 (10 min) | How long before a game times out. |
| `COMMAND_COOLDOWN_SECONDS` | `cogs/crossword_cog/config.py` | 10 | Cooldown between crossword starts per channel. |
| `WORDS_PER_GAME_MIN` / `WORDS_PER_GAME_MAX` | `cogs/crossword_cog/config.py` | 4 / 6 | Range for random word count. |
| `MAX_PLACEMENT_ATTEMPTS` | `cogs/crossword_cog/config.py` | 200 | Max retries for grid generation. |
| `DIFFICULTIES` | `cogs/crossword_cog/config.py` | `{beginner, advanced}` | Difficulty configs (label, reveal fraction). |
| `DEFAULT_DIFFICULTY` / `DEFAULT_LANGUAGE` | `cogs/crossword_cog/config.py` | `beginner` / `es` | Defaults when user doesn't specify. |

No environment variables — all config is baked into `config.py`.

## Persistent views

None. The crossword uses ephemeral in-game state tracked in
`self._active` (a dict keyed by `channel_id`). The Components V2 layout
view (`use_v2=True`) is created per-game but has a timeout matching the
game timeout — it's not persistent across restarts.

## Known edge cases & gotchas

- **One game per channel**: A second `$crossword` in the same channel is
  rejected with an error message. The first game must end (solved,
  timeout, quit, reveal) before a new one can start.
- **Multi-word answers**: The word pool includes some multi-word entries.
  These are filtered out during grid generation (see `_build_game`) to
  avoid placement failures. If you add new words, ensure single-token
  answers or handle splits in the grid logic.
- **Accent normalization**: Answers are normalized (accents stripped,
  lowercased, non-alphanumerics removed) for matching. Players can type
  "cafe" or "café" and both match "café".
- **Hint limit**: Max 2 hints per game. The 3rd `!hint` returns a "no
  more hints" message. This is a per-game counter, not per-user.
- **Timezone**: `crossword_games.started_at` and `ended_at` are
  `TIMESTAMPTZ` (unlike legacy league tables). Leaderboard scopes
  (`week`, `month`, `<N> days`) use `NOW() - INTERVAL` SQL correctly.
- **Restart recovery**: If a game is interrupted, the `game_id` is
  **not** written to `crossword_games` with `completion="interrupted"`.
  The row is simply deleted from `crossword_active_games`. To track
  interrupted games historically, see commit `0d687f9` for the recovery
  logic.
- **V2 render hang**: Components V2 rendering (`use_v2=True`) can hang
  if called from within the timeout watcher task. The timeout fallback
  sends a plain embed instead. See commits `6294726`, `a40efef`,
  `71e3bf5`, `6a01301` for the debugging history.

## Testing & debugging

- **`$cwtimeout <seconds>`**: Override the default 600s timeout for the
  current process lifetime. Useful for rapid testing. Example:
  `$cwtimeout 30` sets a 30-second timeout.
- **Word pool inspection**: Query `crossword_words` directly in the DB
  or use `$cwwords unseen es` to find words that have never been used in
  a game.
- **Active game inspection**: Query `crossword_active_games` to see if a
  game is "stuck" (row exists but no activity). The recovery flow only
  runs on cog load, so mid-session leaks require manual cleanup.

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [`../admin.md`](../admin.md) — admin command reference.
- [`../database.md`](../database.md) — schema details.
- [`./league.md`](./league.md) — another feature with competitive
  leaderboards.
