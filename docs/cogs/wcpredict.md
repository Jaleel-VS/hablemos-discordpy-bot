# World Cup Predictions (`wcpredict_cog`)

Lets users save a private prediction for the World Cup champion, and (after
an admin records the actual winner) shows a public leaderboard of who
called it.

## Overview

`/wcpredict` is the prediction-flavored sibling of [`/worldcup`](./
). Where `/worldcup` grants a Discord team role, `/wcpredict` only writes
to the database — it does not touch any roles. Both features share the
same `Team X` role-name convention to discover the list of teams.

The flow has three phases:

1. **Open** — predictions are editable. Each user has at most one pick.
2. **Locked** — once `wc_predict.deadline_ts` has passed, picks become
   read-only. `/wcpredict view` still works; the leaderboard shows
   per-team distribution but not per-user picks.
3. **Graded** — once an admin runs `$wcpredict setwinner`, the
   leaderboard reveals every user's pick with ✅/❌ and the running
   tally.

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/wcpredict set` | Open the picker (paginated select, 24/page). Save, change, or clear your pick. Locked after the deadline. | None | None |
| `/wcpredict view` | Show your current pick (ephemeral). | None | None |
| `/wcpredict leaderboard` | Pre-grading: per-team pick distribution. Post-grading: full standings with ✅/❌. | None | None |

### Admin commands

Owner-only prefix group. See [`../admin.md`](../admin.md#wcpredict-group-owner-only).

| Command | Description |
|---------|-------------|
| `$wcpredict setdeadline <ISO\|epoch>` | Set the lock timestamp. |
| `$wcpredict cleardeadline` | Remove the deadline. |
| `$wcpredict setwinner <team>` | Record the champion + grade picks. |
| `$wcpredict clearwinner` | Reset the recorded champion. |
| `$wcpredict stats` | Participation totals + per-team distribution. |

## Listeners & flows

No listeners — purely command-driven.

**Set flow:**
1. User runs `/wcpredict set`.
2. Cog reads the deadline from `bot_settings` (key `wc_predict.deadline_ts`).
3. If locked, responds with the locked-in pick (or "you didn't lock one in"). Otherwise opens the menu.
4. On select, `WCPredictTeamSelectView` upserts via
   `db.upsert_wc_prediction(user_id, guild_id, role_id, role_name)` and
   posts a log embed to the World Cup log channel.

**Grading flow:**
1. Admin runs `$wcpredict setwinner <team>`.
2. Cog resolves the team to a `Team X` role and writes its ID to
   `bot_settings` (key `wc_predict.winner_role_id`).
3. Iterates all predictions, applies `score_prediction()` (1 point for
   the correct champion, otherwise 0), and reports the count.
4. Posts a summary embed to the log channel.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `wc_predictions` | `WCPredictionsMixin` | One row per user; stores the picked `Team X` role ID and a denormalized `team_name` snapshot so the leaderboard still renders if the role is later deleted. |

State that doesn't deserve its own table lives in `bot_settings`:

| Key | Type | Meaning |
|-----|------|---------|
| `wc_predict.deadline_ts` | BIGINT (Unix epoch seconds) | 0 or unset = no deadline; otherwise the lock timestamp. |
| `wc_predict.winner_role_id` | BIGINT (role ID) | 0 or unset = un-graded; otherwise the actual champion. |

See [`../database.md`](../database.md#wc_predictions) for the SQL.

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `WC_PREDICT_DEFAULT_DEADLINE_TS` | `cogs/wcpredict_cog/config.py` | `0` | Optional fallback deadline (Unix epoch). `bot_settings` overrides this when set. |
| `WORLD_CUP_LOG_CHANNEL_ID` | `cogs/worldcup_cog/config.py` | (baked-in) | Reused — set/clear/grade events log here. |

## Persistent views

None. Both views (`WCPredictMenuView`, `WCPredictTeamSelectView`) use the
default 180s timeout and are created per-interaction.

## Known edge cases & gotchas

- **`/wcpredict` is independent from `/worldcup`.** Predicting a team
  does not grant the team role, and vice versa.
- **Pre-grading privacy.** The leaderboard never lists individual users
  before `$wcpredict setwinner` is run — only aggregate counts.
- **Role deleted between save and grade.** The `team_name` snapshot
  keeps the leaderboard readable; grading still works because we
  compare role IDs, not names.
- **Deadline = 0.** Treated as "never locked" by `_is_locked()`. Setting
  via `cleardeadline` writes 0; clearing the env var leaves it 0 too.
- **Member left the server.** Their row stays. The leaderboard falls
  back to a raw `<@id>` mention.
- **Time zone handling.** `setdeadline` interprets naive ISO datetimes
  as UTC. Use the `Z` suffix or an explicit offset to avoid surprises.

## Testing & debugging

```text
$wcpredict setdeadline 2026-06-11T18:00:00Z
$wcpredict stats
$wcpredict setwinner Brazil
$wcpredict clearwinner
$wcpredict cleardeadline
```

`scoring.score_prediction()` is a pure function and can be unit-tested
without Discord/DB.

## Related

- [`./worldcup.md`](./worldcup.md) — the role-granting sibling that
  defines the `Team X` role convention. *(Note: this file may not exist
  yet; see `cogs/worldcup_cog/` directly.)*
- [`../commands.md`](../commands.md) — user command reference.
- [`../admin.md`](../admin.md) — admin command reference.
- [`../database.md`](../database.md) — schema reference.
