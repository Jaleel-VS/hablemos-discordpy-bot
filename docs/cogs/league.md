# Language League (`league_cog`)

Competitive language-learning tracking system where users earn points by
chatting in their target language.

## Overview

The Language League encourages consistent language practice through
friendly competition. Members opt in to one of two leagues (Spanish or
English) based on their learning language, then earn points for every
message they send in their target language that meets quality
thresholds. Rounds last one week (Sunday to Sunday), and the top
performers in each league earn a champion role — with a one-week
cooldown to keep the competition fresh.

Key mechanics:

- **Language detection** via `langdetect`. Only messages in the target
  language count (no code-switching or off-topic chatter).
- **Anti-spam**: 60-second cooldown per channel, 100-message daily cap,
  10-character minimum length.
- **Scoring**: 1 point per message + 5 bonus points per active day.
- **Role requirements**: Must have exactly one learning role (Spanish or
  English) and must not be native in that language.
- **Channel exclusions**: Admins can exclude channels (e.g., bot spam
  channels) from point tracking.

The system runs entirely in-guild on a single configured server (see
`LEAGUE_GUILD_ID`).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/league join` | Opt into the league (validates roles, creates DB entry). Also available via persistent button. | Learning role required | None |
| `/league leave` | Opt out of the league (DB only; keeps historical stats). | None | None |
| `/league view` | Show current leaderboard image (cached for 30s) with combined or league-specific rankings. | None | None |
| `/league stats [@user]` | View your stats or another user's: round score, all-time score, active days, message count, rank. | None | None |

All slash commands are guild-scoped to `LEAGUE_GUILD_ID` for instant
sync.

### Admin commands

Owner-only. All under the `$league` group. See
[`../admin.md`](../admin.md) for full reference.

- **`ban` / `unban`** — ban/unban a user from the league (updates DB +
  in-memory cache).
- **`exclude` / `include` / `excluded`** — manage channel exclusions.
- **`admin_stats`** — high-level stats: participant count, 30-day
  message volume, excluded channels.
- **`validatemessage`** — debug language detection for a specific
  message (fetch message by link, run detection, show result).
- **`audit`** — show a user's last 3 counted messages with language
  details and jump links.
- **`endround`** — manually end the current round (save winners, assign
  roles, create next round, announce).
- **`seedrole`** — seed the last-round role recipients set (used during
  role-cooldown setup).
- **`preview`** — dry-run the round-end announcement without pinging or
  mutating state.
- **`reminder [#channel]`** — post a persistent "Join the League!"
  button + embed.
- **`recent [limit]`** (aliases: `joiners`, `joins`) — last N first-time
  joiners (default 10, max 25).
- **`topchannels [days]`** (alias: `topchans`) — top 15 channels by
  message volume over a window, rendered as a horizontal bar chart
  PNG (excluded channels shown in red).
- **`heatmap [days]`** (alias: `hm`) — 7×24 day-of-week × hour activity
  heatmap (UTC), rendered as a PNG with seaborn.

## Listeners & flows

### `on_message` → activity tracking

Every message in the league guild triggers a scoring check:

1. **Pre-checks** (cheap, cached):
   - Channel not excluded?
   - User opted in?
   - User not banned?
   - Author is a member (not a bot, webhook, etc.)?
2. **Quality checks**:
   - Message ≥10 characters (after stripping custom/Unicode emoji)?
   - User hasn't hit the 100-message daily cap?
   - 60-second channel cooldown elapsed?
3. **Language detection** (`langdetect`):
   - Detects language of the message body.
   - Matches user's learning language?
4. **Record activity**: insert row into `leaderboard_activity`, increment
   in-memory cooldown cache, invalidate leaderboard cache.

Errors are logged server-side; the user never sees a failure message
(silent success/skip).

### Scheduled round-end check

A `tasks.loop` runs every 1 minute (configurable via
`ROUNDS.ROUND_CHECK_INTERVAL_MINUTES`). If the current round's
`end_date` has passed:

1. Fetch top 10 users per league (Spanish, English) for the round.
2. Save top 3 as winners (`leaderboard_round_winners`).
3. Mark round as ended (`leaderboard_rounds.ended_at`).
4. Manage roles:
   - Remove champion role from last round's recipients.
   - Add champion role to this round's top 3 eligible (skip anyone who
     won last round).
5. Mark new role recipients in `leaderboard_round_recipients`.
6. Post announcement to configured `WINNER_CHANNEL_ID` with leaderboard
   + pings.
7. Create next round (start now, end next Sunday noon).

### Persistent join button

The `LeagueJoinView` is registered once in `__init__` with a stable
custom ID (`league:join_button`). Clicks survive bot restarts. The
callback delegates to `perform_join(member)` — the same logic as
`/league join`.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `leaderboard_users` | `LeaderboardMixin` | One row per user who has ever joined. Tracks `opted_in`, `banned`, `learning_spanish`, `learning_english`, `joined_at`. |
| `leaderboard_activity` | `LeaderboardMixin` | One row per counted message. Columns: `user_id`, `message_id`, `channel_id`, `created_at`, `points`. Note: `created_at` is naive `TIMESTAMP` (see [known issues](#known-edge-cases--gotchas)). |
| `leaderboard_excluded_channels` | `LeaderboardMixin` | Channels ignored by activity tracking. |
| `leaderboard_rounds` | `LeaderboardMixin` | One row per round. Tracks `round_number`, `start_date`, `end_date`, `ended_at`, `created_at`. |
| `leaderboard_round_winners` | `LeaderboardMixin` | Top 3 users per league per round (for historical record). |
| `leaderboard_round_recipients` | `LeaderboardMixin` | Users who received the champion role in a given round (for cooldown logic). |

See [`../database.md`](../database.md) for query methods (all in
`LeaderboardMixin`).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `LEAGUE_GUILD_ID` | `cogs/league_cog/config.py` | (baked-in) | Guild where the league runs. |
| `WINNER_CHANNEL_ID` | `cogs/league_cog/config.py` | (baked-in) | Channel for round-end announcements. |
| `CHAMPION_ROLE_ID` | `cogs/league_cog/config.py` | (baked-in) | Role awarded to top 3 per league. |
| `ROLES.*` | `cogs/league_cog/config.py` | (baked-in) | Native/learner role IDs (used for validation). |
| `SCORING.*` | `cogs/league_cog/config.py` | 1 pt/msg, 5 pt/day | Scoring multipliers. |
| `RATE_LIMITS.*` | `cogs/league_cog/config.py` | 60s cooldown, 100 msg/day cap | Anti-spam thresholds. |
| `ROUNDS.*` | `cogs/league_cog/config.py` | 7-day rounds, 1-min checks | Round duration and check frequency. |
| `LANGUAGE.LANGDETECT_SEED` | `cogs/league_cog/config.py` | `0` | Seed for consistent `langdetect` results. |

All IDs accept environment variable overrides via helpers from
`config.py` (`get_int_env`).

## Persistent views

- **`LeagueJoinView`**: Custom ID `league:join_button`. Registered once
  in `__init__` via `bot.add_view(...)` with `timeout=None`. Survives
  restarts.

## Known edge cases & gotchas

- **Timezone drift**: `leaderboard_activity.created_at` is naive
  `TIMESTAMP` (no `TIMESTAMPTZ`). If you query by date/time windows,
  you'll get results in the DB's timezone (typically UTC). Newer schemas
  use `TIMESTAMPTZ` — this table predates that convention. See
  [`../playbook.md`](../playbook.md) for migration guidance if the drift
  becomes problematic.
- **Daily cap reset**: The 100-message daily cap resets at midnight UTC
  (keyed on `DATE(created_at)`). Users in other timezones may see the
  cap reset at odd hours.
- **Role cooldown**: Users who win in round N cannot earn the champion
  role again until round N+2 (one-week rest). They can still compete and
  appear in the top 3 leaderboard, just not receive the role.
- **Leaderboard cache**: View/stats commands cache leaderboard data for
  30 seconds. If you update scores manually via DB, the cache won't
  reflect it until the TTL expires. Admin commands that mutate state
  (e.g., `endround`) invalidate the cache explicitly.
- **Language detection false positives**: Short messages or mixed
  languages may mis-detect. The `$league validatemessage` and
  `$league audit` commands help debug these. Consider raising the
  minimum length (`RATE_LIMITS.MIN_MESSAGE_LENGTH`) if false positives
  are common.

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [`../admin.md`](../admin.md) — admin command reference.
- [`../database.md`](../database.md) — schema details.
- [`../architecture.md`](../architecture.md) — cog loading,
  `on_message` listener patterns.
- [`./crossword.md`](./crossword.md) — another feature with per-game
  leaderboards.
