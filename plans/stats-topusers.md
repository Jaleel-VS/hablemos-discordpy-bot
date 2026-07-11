# Plan: `$stats topusers` — top 10 most active users by message count

Status: planned, not implemented.

## Why this needs a new table (verified against current schema)

Checked both existing tables `stats_cog` writes to — neither can answer
"top N users by message count over the last N days":

- `user_activity` (`db/schema.py`, `db/stats.py::upsert_user_activity`)
  tracks only `first_seen`/`last_seen` per user — **no counter, no
  time-bucketing**. It answers "is this user active", not "how active".
- `channel_stats` counts messages, but is keyed by `channel_id` +
  `role_type` + `hour_bucket` — **no `user_id` column**. Adding one
  would double-purpose a table that every other `$stats` subcommand
  already depends on; higher blast radius than a new table.

Decision: add a new table, `user_message_counts`, mirroring
`channel_stats`'s existing shape (hour-bucketed counter, same
`ON CONFLICT ... DO UPDATE` upsert pattern) but keyed by `user_id`
instead of `channel_id`. This is the smallest correct change — same
pattern already proven in this codebase, no touch to existing tables.

## Phase 1 — Schema (`db/schema.py`)

Add immediately after the existing `channel_stats` table block (find
it via `CREATE TABLE IF NOT EXISTS channel_stats`):

```sql
CREATE TABLE IF NOT EXISTS user_message_counts (
    user_id      BIGINT NOT NULL,
    hour_bucket  TIMESTAMPTZ NOT NULL,
    msg_count    INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, hour_bucket)
)
```

Add a matching index, mirroring `idx_channel_stats_bucket`:

```sql
CREATE INDEX IF NOT EXISTS idx_user_message_counts_bucket
ON user_message_counts(hour_bucket)
```

No `role_type` column — this subcommand doesn't break down by role,
so don't add a column nothing reads (matches AGENTS.md: don't add
speculative fields).

## Phase 2 — DB mixin (`db/stats.py`)

Two additions to `StatsMixin`:

1. **Upsert method**, same pattern as `upsert_channel_stat` (lines
   15-29), adapted for the new table:

```python
async def upsert_user_message_count(
    self, user_id: int, hour_bucket: datetime
) -> None:
    """Increment message count for a user/hour bucket."""
    await self._execute(
        """
        INSERT INTO user_message_counts (user_id, hour_bucket, msg_count)
        VALUES ($1, $2, 1)
        ON CONFLICT (user_id, hour_bucket)
        DO UPDATE SET msg_count = user_message_counts.msg_count + 1
        """,
        user_id,
        hour_bucket,
    )
```

2. **Query method**, same pattern as `get_top_channels` (lines 48-64),
   adapted for `user_id`:

```python
async def get_top_users(
    self, days: int = 7, limit: int = 10
) -> list[dict]:
    """Top users by total message count in the last N days."""
    rows = await self._fetch(
        """
        SELECT user_id, SUM(msg_count) AS total
        FROM user_message_counts
        WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT $2
        """,
        str(days),
        limit,
    )
    return [dict(r) for r in rows]
```

Place both methods in the "Channel stats queries" section (or add a
new "User message-count queries" subsection directly after it) — do
not put them under "User adoption queries" (that section is about
`user_activity`, a different table).

## Phase 3 — Wire into the listener (`cogs/stats_cog/main.py`)

In `on_message` (lines 50-71), add the new upsert call alongside the
two existing ones (`upsert_channel_stat`, `upsert_user_activity`) —
same `try/except` block, don't add a second one:

```python
await self.bot.db.upsert_channel_stat(
    message.channel.id, role_type, hour_bucket
)
await self.bot.db.upsert_user_activity(member.id, role_type)
await self.bot.db.upsert_user_message_count(member.id, hour_bucket)
```

`hour_bucket` is already computed earlier in the function — reuse it,
don't recompute.

## Phase 4 — Command (`cogs/stats_cog/main.py`)

Add a new subcommand immediately after `stats_channels` (lines
126-149), matching its exact shape (docstring format, `days` clamp,
embed style, `@commands.is_owner()` — `cog_check` already restricts
to `STATS_GUILD_ID`, but every other subcommand in this cog *also*
carries an explicit `@commands.is_owner()` decorator; keep that
convention rather than relying on `cog_check` alone):

```python
@stats.command(name="topusers")
@commands.is_owner()
async def stats_topusers(self, ctx: commands.Context, days: int = 7):
    """Top active users leaderboard. Usage: $stats topusers [days]"""
    days = max(1, min(days, 90))
    data = await self.bot.db.get_top_users(days, limit=10)

    if not data:
        await ctx.send(embed=red_embed("No user activity data yet."))
        return

    user_lines = []
    for i, row in enumerate(data, 1):
        member = ctx.guild.get_member(row["user_id"]) if ctx.guild else None
        name = member.display_name if member else f"<@{row['user_id']}>"
        user_lines.append(f"`{i}.` {name} — **{row['total']:,}** msgs")

    embed = discord.Embed(
        title=f"📊 Top Users — Last {days} days",
        color=0x5865F2,
    )
    embed.add_field(name="🏆 Most Active", value="\n".join(user_lines), inline=False)
    await ctx.send(embed=embed)
```

Notes on this block (read before implementing, don't deviate):
- Mirrors `stats_channels`'s member-resolution pattern (`ctx.guild.get_channel`
  → here `ctx.guild.get_member`), including the same `if ctx.guild else None`
  guard and fallback string when the member isn't resolvable — a user
  who left the server still has rows in `user_message_counts`, and the
  fallback must not crash (AGENTS.md: bounds-check /
  handle-`None`-at-the-boundary rule).
- `days` clamp range (1-90) matches every other subcommand in this
  file — don't invent a different range for this one.
- No chart/graph version needed for this feature (unlike
  `stats_channels`, which has a `graphs.render_top_channels` bar-chart
  counterpart) — this is a text-embed-only leaderboard. Do not add a
  `graphs.py` function for this unless asked; that would be scope
  creep beyond what's specified here.

## Acceptance check (what "done" looks like)

1. `ruff check cogs/stats_cog/ db/stats.py db/schema.py` — clean.
2. `$stats topusers` in the tracked guild returns a leaderboard embed
   with up to 10 users, ranked by message count, for the last 7 days
   (default).
3. `$stats topusers 30` returns the same, scoped to 30 days.
4. `$stats topusers` in a channel where there's no `user_message_counts`
   data yet returns the "No user activity data yet." embed, not a
   crash.
5. A user who left the server still appears in the leaderboard (by
   mention fallback, not a `None`-crash) if they have historical rows.
6. No changes to `channel_stats`, `user_activity`, or any other
   existing `$stats` subcommand's behavior.
7. Docs updated in the same commit, per `docs/CONTRIBUTING.md`'s
   trigger table (checked — this change hits two rows, and both land
   on a **pre-existing gap**: the stats cog (added in a prior commit)
   was never documented at all — no `docs/cogs/stats.md`, no `$stats`
   entry in `docs/admin.md`, no `channel_stats`/`user_activity`
   section in `docs/database.md`). Do not fix that entire pre-existing
   gap as part of this plan — only document what this plan adds:
   - Add one row for `$stats topusers` to `docs/admin.md`, matching
     the table format already used there for other owner-only
     commands (see the `$mystats` row for the simplest example of that
     format — command + one-line description + "Owner-only" tag).
   - Add a `### Stats tracking` subsection to `docs/database.md`
     under `## Key tables` (see `### Vocab Catch` for the target
     format: table name, columns, purpose, one line on what writes to
     it). Cover `user_message_counts` (the table this plan adds) —
     do not also backfill documentation for `channel_stats` /
     `user_activity`; that's the pre-existing gap, out of scope here.
8. No test file exists for `stats_cog` today (checked: no
   `tests/stats/` directory) — do not add one speculatively; matching
   existing coverage for this cog is out of scope for this plan.

## Explicitly out of scope (do not implement)

- A `graphs.py` bar-chart version of this leaderboard.
- Any change to `STATS_GUILD_ID` gating, `cog_check`, or the existing
  subcommands (`channels`, `roles`, `growth`, `heatmap`).
- Backfilling `user_message_counts` from historical `channel_stats`
  data — the new table starts empty and populates going forward only.
