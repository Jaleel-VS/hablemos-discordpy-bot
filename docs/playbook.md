# Operational Playbook

Runbook for diagnosing and recovering from common failure modes.

## Reading production logs

Many checks below say "check Railway logs." Railway has only ~7 days of
in-app retention and no native log drain, so to grep/query logs (from a
script or an agent session) use the puller, which hits Railway's public
GraphQL API:

```bash
# RAILWAY_TOKEN / RAILWAY_SERVICE_ID / RAILWAY_ENVIRONMENT_ID must be set
# (see deployment.md → "Querying Railway logs programmatically";
#  run `python scripts/railway_logs.py --discover` to find the IDs).
python scripts/railway_logs.py --limit 1000 | grep "poll failed"
python scripts/railway_logs.py --filter "@level:error" --json
```

It resolves the latest deployment automatically. See
[`deployment.md`](./deployment.md) for setup and token notes.

## Bot won't start

### Symptom

`hablemos.py` exits immediately or hangs during startup. Railway logs
show errors or no "I'm online" message.

### Checks

1. **Database connection**: Check the logs for `asyncpg` connection
   errors (`python scripts/railway_logs.py --filter asyncpg`). The bot
   retries DB connection 5 times with exponential
   backoff (see `setup_hook` in `hablemos.py`). If all retries fail,
   the bot exits.
   - Verify `DATABASE_URL` env var is set and correct.
   - Check Railway's PostgreSQL add-on status. If the DB is restarting
     or unhealthy, wait for it to stabilize.
   - Test the connection string locally:
     ```bash
     psql $DATABASE_URL -c "SELECT 1;"
     ```
2. **Missing required env vars**: `BOT_TOKEN` and `DATABASE_URL` are
   required. Others have defaults (see [`deployment.md`](./deployment.md)).
   - Check Railway's environment variables dashboard.
   - If testing locally, ensure `.env` file exists and is loaded.
3. **Schema migration failure**: If a new migration in `db/schema.py`
   has a syntax error or conflicts with existing data, `initialize_schema`
   will fail and the bot will exit.
   - Check logs for PostgreSQL errors (syntax, constraint violations,
     etc.).
   - Roll back recent schema changes or fix the migration SQL.
   - For destructive changes (column drops, type changes), see
     [`database.md`](./database.md) — those should be scripted in
     `scripts/` and run manually, not baked into `schema.py`.
4. **Cog load failure**: If a cog's `main.py` raises an exception during
   import or `setup()`, the bot will fail to start.
   - Check logs for `ImportError`, `NameError`, `AttributeError`, etc.
   - If you recently added a new cog, verify its `__init__.py` exists
     and `setup(bot)` is defined.
   - Try disabling the problematic cog via `$cog disable <name>` in a
     previous deploy, then redeploy with the fix.

## Cog is disabled

### Symptom

Commands from a specific cog return "command not found" or don't
autocomplete. The cog's features are unavailable.

### Cause

The cog is in the database-backed "disabled cogs" set (managed by
`$cog disable` / `$cog enable`). The bot skips loading disabled cogs on
startup.

### Recovery

1. Check the disabled-cogs set:
   ```bash
   $cog list
   ```
   (Owner command — runs in any channel the bot can see.)
2. Re-enable the cog:
   ```bash
   $cog enable <cog_name>
   ```
   Example: `$cog enable LeagueCog`.
3. Reload the cog to make it active immediately:
   ```bash
   $cog reload <cog_name>
   ```
   Or restart the bot (redeploy on Railway).

> **Why disable instead of unload?** Unloading a cog temporarily removes
> it from memory but doesn't persist across restarts. Disabling writes
> to the `settings` table so the cog stays off until explicitly
> re-enabled.

## Crossword game is "stuck"

### Symptom

A crossword game started but never ended. The channel shows an old game
embed and players can't start a new game (get "a game is already active"
error).

### Diagnosis

1. Check `crossword_active_games` for a row with the stuck channel's ID:
   ```sql
   SELECT * FROM crossword_active_games WHERE channel_id = <channel_id>;
   ```
2. If a row exists, the game state is stale (likely the timeout watcher
   task failed or the bot restarted mid-game without triggering the
   interrupt recovery flow).

### Recovery

**Option A: Wait for the next bot restart.** The `_recover_interrupted_games`
flow (in `crossword_cog/main.py`) will notify players and clear the row
automatically.

**Option B: Manual cleanup** (if you can't wait):

1. Delete the stale row:
   ```sql
   DELETE FROM crossword_active_games WHERE channel_id = <channel_id>;
   ```
2. Post a message in the channel explaining the game was cancelled due
   to a technical issue.
3. Players can now start a new game.

> **Prevention**: If crossword games frequently get stuck, check the
> logs for `asyncio` task cancellation errors or timeout-related
> exceptions (`python scripts/railway_logs.py --filter asyncio`). The
> timeout watcher is robust, but ungraceful restarts (OOM kills,
> SIGKILL) can orphan game state.

## Slash commands not syncing

### Symptom

New slash commands don't appear in the Discord UI, or old commands that
were removed still show up.

### Cause

Slash commands are **not** auto-synced on bot startup. Syncing requires
an explicit owner command.

### Recovery

1. Run the sync command:
   ```bash
   $sync
   ```
   (Owner command — syncs global commands to Discord's API.)
2. Wait 5–10 minutes for Discord to propagate the changes. Global
   command sync is not instant.
3. For guild-specific commands (e.g., Language League commands scoped to
   `LEAGUE_GUILD_ID`), sync is instant when the bot starts. No manual
   sync needed.

> **Don't sync in `on_ready`**: The bot intentionally does *not* call
> `tree.sync()` in `on_ready` to avoid rate limits. See `AGENTS.md` for
> the pattern.

## Timezone drift in queries

### Symptom

Time-filtered queries (e.g., "last 7 days") return unexpected results.
Dates are off by several hours.

### Cause

**Legacy tables** (e.g., `leaderboard_activity.created_at`) use naive
`TIMESTAMP` (no timezone info). Postgres stores them in the DB's
timezone (typically UTC) but doesn't label them as such. When you query
with `NOW()` or `CURRENT_TIMESTAMP`, you're comparing a `TIMESTAMPTZ`
to a `TIMESTAMP`, which can cause off-by-hours drift.

**Newer tables** (e.g., `crossword_games.started_at`) use `TIMESTAMPTZ`
and don't have this issue.

### Workaround

For legacy `TIMESTAMP` columns, explicitly cast to `TIMESTAMPTZ` with
the correct timezone in queries:

```sql
-- Bad (compares TIMESTAMPTZ to TIMESTAMP, may drift)
SELECT * FROM leaderboard_activity
WHERE created_at > NOW() - INTERVAL '7 days';

-- Good (explicit UTC cast)
SELECT * FROM leaderboard_activity
WHERE created_at AT TIME ZONE 'UTC' > NOW() - INTERVAL '7 days';
```

Or add a migration to alter the column type (see
[`database.md`](./database.md) for migration rules).

### Which tables are affected?

As of 2025-05-09:

- `leaderboard_activity.created_at` — **TIMESTAMP (no TZ)**
- `crossword_games.started_at`, `crossword_games.ended_at` — **TIMESTAMPTZ (correct)**
- `crossword_word_events.solved_at` — **TIMESTAMPTZ (correct)**
- `command_metrics.timestamp` — check schema; likely **TIMESTAMP**

See the "Known edge cases" sections in [`cogs/league.md`](./cogs/league.md)
and [`cogs/crossword.md`](./cogs/crossword.md) for per-feature notes.

## Language League leaderboard is stale

### Symptom

`/league view` shows outdated scores. A user just earned points but the
leaderboard doesn't reflect it.

### Cause

The leaderboard is cached for 30 seconds (see
`LeagueCog.LEADERBOARD_CACHE_TTL`). The `on_message` listener invalidates
the cache on every counted message, but if you manually update
`leaderboard_activity` via SQL, the cache won't know.

### Recovery

Wait 30 seconds for the cache to expire naturally, or restart the bot
(which clears in-memory caches).

> **Why cache?** The leaderboard query is expensive (joins, aggregations
> over thousands of rows). Caching avoids hammering the DB on every
> `/league view` call.

## Round-end announcement didn't post

### Symptom

The Language League round ended (past the `end_date`) but no
announcement was posted in the winner channel.

### Diagnosis

1. Check the logs for errors in `check_round_end` task (runs every
   1 minute): `python scripts/railway_logs.py --filter check_round_end`.
2. Common causes:
   - `WINNER_CHANNEL_ID` is wrong or the bot lacks permissions to post
     in that channel.
   - The guild or champion role couldn't be fetched (IDs mismatched or
     bot not in the guild).
   - DB query failure during `process_round_end`.

### Recovery

1. Manually trigger the round end:
   ```bash
   $league endround
   ```
   (Owner command — processes the round end, assigns roles, and posts
   the announcement.)
2. If the command fails, check logs for the specific error (missing
   channel, role, permissions, DB constraint violation, etc.) and fix
   the root cause.

> **Prevention**: Test round-end logic with `$league preview` (dry-run,
> no mutation) before the actual round end. Verify the winner channel
> and champion role exist.

## World Cup bets not settling / payouts stuck

### Symptom

A finished match's bets stay `pending` — users report they "haven't been
paid out." The results poller runs every `WCBET_RESULTS_POLL_MINUTES`
but the match never gets a result row.

### Diagnosis

1. **Is it actually unsettled?** Check for a result row and pending bets:
   ```sql
   SELECT * FROM wc_match_results WHERE match_id = <id>;
   SELECT match_id, status, COUNT(*), SUM(stake)
   FROM wc_bets WHERE match_id = <id> GROUP BY match_id, status;
   ```
   `get_wc_pending_unsettled()` (used by `$wcbetadmin`) lists all
   matches with pending bets and no result.
2. **Does ESPN have the match completed?** The poller settles only when
   it matches a completed ESPN event by exact `(kickoff_utc, home,
   away)`. If the match isn't really finished, manual settlement is
   expected — not a bug. Verify via the scoreboard:
   `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD`
   (the ET calendar date, same as the fixture's `date`).
3. **Is the poller erroring?** Check the logs:
   ```bash
   python scripts/railway_logs.py --limit 1000 | grep "poll failed"
   ```
   A repeating `World Cup results poll failed` traceback means the
   poll→settle path is throwing every cycle (and rolling back, so no
   payout lands). The settlement runs in one transaction, so a late
   failure rolls back the credits too — the same `bet_won` log lines
   reappearing every poll is the tell.
4. **Is it a settle-mode issue?** `WCBET_AUTO_SETTLE=0` (default) only
   *proposes* a settle (`$wcbetadmin result …`) in the log channel; it
   doesn't auto-pay. Set `WCBET_AUTO_SETTLE=1` to settle automatically.
   Env changes need a redeploy — the value is read once at startup.

> **Gotcha (fixed 2026-06-14):** `settle_wc_match` / `void_wc_match`
> selected candidate parlays with `SELECT DISTINCT … FOR UPDATE`, which
> Postgres rejects (`FeatureNotSupportedError: FOR UPDATE is not allowed
> with DISTINCT clause`). Any match with a parlay leg crashed mid-
> transaction and never settled. `tests/wcbet/test_sql_guards.py` now
> guards against `FOR UPDATE` + `DISTINCT` in the db layer; the fakes
> can't catch Postgres-only SQL errors, so also run the real-Postgres
> integration tests (`python scripts/run_pg_integration_tests.py`, needs
> the Docker daemon) when touching settlement SQL.

### Recovery

1. **Settle manually** (works regardless of poller state — it's a direct
   command, not the loop):
   ```bash
   $wcbetadmin result <match_id> <home>-<away>
   ```
   e.g. `$wcbetadmin result 25 7-1`. This settles every pending bet on
   the match at its stored odds, pays winners, resolves parlay legs, and
   announces it.
2. If the poller was crashing, deploy the fix and **redeploy** — the
   poller catches up on its next run (settles all backlogged matches
   when `WCBET_AUTO_SETTLE=1`).
3. To refund instead of settle (e.g. abandoned match):
   `$wcbetadmin void <match_id>`.

## TODOs

> Seed this section as incidents occur or as you discover edge cases
> that aren't covered above.

- **How to investigate a message that didn't count toward the league**:
  Check `$league audit <user>` for recent counted messages and
  `$league validatemessage <message-link>` to debug language detection
  for a specific message.
- **Recovering from a bad schema migration**: (Wait for a real incident
  to document. For now: roll back the deploy, fix the SQL, redeploy.)
- **Handling a spam wave in crossword games**: (Document once we have
  abuse patterns. Consider per-user rate limits.)
- **Backing up and restoring the database**: (Railway has automated
  backups; document the restore process once tested.)
- **Monitoring metrics and alerting**: (Future: integrate with a
  metrics/logging service, or ship logs to Axiom/BetterStack via the
  Locomotive sidecar for persistent search + alerts. For now: pull logs
  on demand with `scripts/railway_logs.py` and manual checks.)

## Related

- [`deployment.md`](./deployment.md) — env vars, boot sequence, logs.
- [`database.md`](./database.md) — schema, migrations, query patterns.
- [`architecture.md`](./architecture.md) — cog lifecycle, error
  handling, task loops.
- [`commands.md`](./commands.md) & [`admin.md`](./admin.md) — command
  references for recovery operations.
