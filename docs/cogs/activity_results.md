# Activity Results (`activity_results_cog`)

Posts finished **daily** Activity game results (e.g. Wordle) to a configured
channel, mentioning the player.

## Overview

The [Activity](../activity.md) (embedded app) can't post channel messages
itself — that's the bot's job. When a player finishes a daily game, the
Activity backend writes a row to `game_results`. This cog polls for unposted
daily rows, posts an emoji-grid card, and marks each posted. The bot stays
gateway-only (no inbound HTTP); it just shares the Activity's PostgreSQL.

Freeplay results are never posted — only `mode = 'daily'` rows, to keep the
channel meaningful and avoid spam.

## Listeners & flows

No listeners. A single `tasks.loop` (`poll_results`) drives everything:

1. Every `ACTIVITY_RESULTS_POLL_SECONDS` (default 60s), if a channel is
   configured, fetch up to `ACTIVITY_RESULTS_BATCH` unposted daily results
   (oldest first).
2. For each, build an embed from the game-agnostic `payload` (`won`,
   `summary`, `grid`) and send it to the channel with a `<@user_id>` mention.
3. Mark the row posted **only after** a successful send, so a transient send
   failure is retried next tick. A row with an unparseable payload is marked
   posted (and logged) so it can't wedge the queue.

The `payload` shape is game-agnostic (every game's `result_payload` includes
`won`/`summary`/`grid`), so this cog posts any game's results without knowing
the game.

## Commands

| Command | Access | Description |
|---------|--------|-------------|
| `$activity_stats` (alias `$astats`) | Owner | Bare call → server totals per game. |
| `$activity_stats totals` | Owner | Per-game counts: games, players, daily/free split, wins, unpublished daily rows. |
| `$activity_stats health` | Owner | Results-poster backlog — unposted daily count, oldest pending age, target channel. |
| `$activity_stats streaks [game_key]` | Owner | Top 10 daily streaks for a game (default `wordle`). |
| `$activity_stats user <member> [game_key]` | Owner | One player's daily games/wins/streaks/distribution (default `wordle`). |

`game_key` is `wordle` or `conjugation`. These are read-only views of the
Activity's own tables; they never write.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `game_results` | Activity backend (read-only here) | One row per finished game. The bot reads unposted daily rows and sets `posted_at`, and aggregates them for `$activity_stats`; it never creates the table (the Activity owns the schema). |
| `game_stats` | Activity backend (read-only here) | Per-`(game_key, user_id)` daily aggregates (games, wins, current/max streak, guess distribution). Read by `$activity_stats streaks`/`user`. |

`GameResultsMixin` (`db/game_results.py`) tolerates the tables not existing yet
(returns empty / zero-valued / no-op) so a fresh environment where the Activity
hasn't booted doesn't error. This includes the `$activity_stats` read methods
(`activity_totals_by_game`, `activity_pending_health`, `activity_top_streaks`,
`activity_user_stats`).

## Configuration & environment variables

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `ACTIVITY_RESULTS_CHANNEL_ID` | `cogs/activity_results_cog/config.py` | `0` | Channel to post to. `0` disables posting (poller no-ops). |
| `ACTIVITY_RESULTS_POLL_SECONDS` | same | `60` | Poll interval. |
| `ACTIVITY_RESULTS_BATCH` | same | `10` | Max results posted per tick. |

## Known edge cases & gotchas

- **Table missing**: If the Activity hasn't created `game_results` yet, the
  poller reads empty and no-ops — no error.
- **Send failure**: On `Forbidden`/`HTTPException` the row is left unposted and
  retried next tick (not marked posted).
- **Malformed payload**: Marked posted + logged, so one bad row can't block the
  queue.
- **Channel unset**: With `ACTIVITY_RESULTS_CHANNEL_ID=0` the loop logs once and
  becomes a no-op.

## Related

- [`../activity.md`](../activity.md) — the Activity and how results are written.
- [`../deployment.md`](../deployment.md) — env var reference.
