# Admin & Owner Commands

Commands restricted to the bot owner (or, where noted, to users with
specific Discord permissions). User-facing commands are in
[`commands.md`](./commands.md).

> **Living-doc rule:** adding, removing, or renaming an admin command
> must update this file in the same commit. See
> [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## `$league` (group, owner-only)

Language League administration. See [`cogs/league.md`](./cogs/league.md)
for the feature itself.

| Subcommand | Description |
|-----------|-------------|
| `$league ban <user>` | Ban a user from the league. Sets `banned=TRUE`, updates in-memory cache. |
| `$league unban <user>` | Lift a league ban. |
| `$league exclude <#channel>` | Stop counting messages in a channel. |
| `$league include <#channel>` | Re-include a previously excluded channel. |
| `$league excluded` | List all currently excluded channels. |
| `$league admin_stats` | Participant breakdown, 30-day message volume, excluded-channel count. |
| `$league validatemessage <message-link>` | Inspect language detection for a specific message. Useful for debugging false positives/negatives. |
| `$league audit <user>` | Show a user's last 3 counted messages with language-detection details and jump links. |
| `$league endround` | Manually end the current round and start the next one. |
| `$league seedrole <id1,id2,…>` | Seed last-round role recipients (used during role-cooldown setup). |
| `$league preview` | Dry-run the round-end announcement without pinging or mutating state. |
| `$league reminder [#channel]` | Post the public "Join the League!" embed with the persistent join button. Defaults to the current channel. |
| `$league recent [limit]` (aliases: `joiners`, `joins`) | Show the N most recent first-time joiners. Default 10, max 25. |
| `$league topchannels [days]` (alias: `topchans`) | Top 15 channels by counted-message volume over a window, rendered as a horizontal bar chart. Excluded channels shown in red. |
| `$league heatmap [days]` (alias: `hm`) | 7×24 day-of-week × hour activity heatmap rendered as a PNG (seaborn). UTC. |

## Crossword admin (owner-only)

Defined directly in `crossword_cog/main.py`. See
[`cogs/crossword.md`](./cogs/crossword.md) for the feature.

| Command | Description |
|---------|-------------|
| `$cwtimeout <seconds>` | Override the crossword timeout for the remaining lifetime of the bot process. Useful for testing. |
| `$cwstats [days\|all]` | Aggregate crossword stats: games, participants, completion breakdown (completed/timeout/quit/interrupted), hints usage, top solvers. |
| `$cwwords <hardest\|easiest\|unseen> [lang] [limit]` | Per-word solve-rate analysis. `unseen` requires a language; others filter optionally. |
| `$cwchart [lang] [days] [min_appearances]` (alias: `cwscatter`) | Scatter plot of per-word solve rate vs average solve time. Rendered as a PNG (seaborn). |

## `$cog` (group, owner-only)

Cog management. See [`cogs/admin.md`](./cogs/admin.md) for the full feature.

| Subcommand | Description |
|-----------|-------------|
| `$cog list` | List all cogs and their status (loaded, disabled, unloaded, protected). |
| `$cog enable <name>` | Enable and load a cog. |
| `$cog disable <name>` | Disable and unload a cog (protected cogs cannot be disabled). |
| `$cog reload <name>` | Reload a cog. |

## `$metrics` (group, owner-only)

Bot usage metrics. See [`cogs/admin.md`](./cogs/admin.md) for the full feature.

| Subcommand | Description |
|-----------|-------------|
| `$metrics [days]` | Command usage summary (default 7 days, max 90). |
| `$metrics hours [days]` | Usage by hour (UTC), rendered as a bar chart. |
| `$metrics user @someone [days]` | Top commands for a user. |
| `$metrics retention` | Show table sizes and retention policy. |
| `$metrics cleanup` | Manually trigger the daily cleanup task. |

## `$task` (group, manage_guild)

Task management. See [`cogs/tasks.md`](./cogs/tasks.md) for the full feature.

| Subcommand | Description |
|-----------|-------------|
| `/task create` | Open a modal to create a task. |
| `/task list [status] [assignee]` | List tasks (filtered by status/assignee). |
| `/task board` | Show a kanban-style board with all tasks grouped by status. |
| `/task delete <task_id>` | Delete a task by ID. |

## `$almightypanel` (manage_guild)

Post the persistent submission button into the trigger channel. See
[`cogs/almighty.md`](./cogs/almighty.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$almightypanel` | Post the persistent submission panel (Submit + Categorize buttons); opens forms that relay to the feed channel. |

## `$langexpanel` / `$langexremove`

Language-exchange admin. See [`cogs/langex.md`](./cogs/langex.md) for the
full feature.

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$langexpanel` | Post the persistent panel (Post / Find / Delete buttons). | `manage_guild` |
| `$langexremove <user>` | Remove a user's language-exchange profile (message + record). | `manage_messages` |

## `$introtracker` (group, manage_messages)

Introduction cooldown enforcement. See [`cogs/intro.md`](./cogs/intro.md) for the full feature.

| Subcommand | Description |
|-----------|-------------|
| `$introtracker add <channel_id>` | Track a channel for intro cooldown enforcement. |
| `$introtracker remove <channel_id>` | Stop tracking a channel. |
| `$introtracker list` | List all tracked channels. |
| `$resetintro <user_id>` (alias: `$clearintro`) | Clear a user's intro history. Allowed with `manage_messages` **or** the Server Staff role (`258819531193974784`). |
| `$introexempt <user_id>` | Exempt a user from intro tracking (requires `manage_messages`). |

## `$wcpredict` (group, owner-only)

World Cup predictions admin. See [`cogs/wcpredict.md`](./cogs/wcpredict.md)
for the full feature.

| Subcommand | Description |
|-----------|-------------|
| `$wcpredict setdeadline <ISO\|epoch>` | Set the prediction lock timestamp. Accepts ISO-8601 (e.g. `2026-06-11T18:00:00Z`) or a Unix epoch in seconds. |
| `$wcpredict cleardeadline` | Remove the deadline (predictions become editable again). |
| `$wcpredict setwinner <team>` | Record the actual champion (role mention, role ID, or `Brazil` / `Team Brazil`). Triggers grading and posts a summary to `#world-cup-log`. |
| `$wcpredict clearwinner` | Reset the recorded champion (un-grades the leaderboard). |
| `$wcpredict stats` | Show participation totals and per-team distribution. |

## `$vocatchadmin` (group, owner-only)

Vocab Catch minigame admin. See [`cogs/vocabcatch.md`](./cogs/vocabcatch.md).

| Subcommand | Description |
|-----------|-------------|
| `$vocatchadmin seed` | Seed the starter card pool (no-op if it already has cards). |
| `$vocatchadmin spawn` | Force a spawn in the **current** channel (must be a configured game channel). |
| `$vocatchadmin addcard <1-5> "<word_es>" <word_en>` | Add a bidirectional card to the pool. |
| `$vocatchadmin preview <card_id> [mode]` | Render a card revealed in a mode (`show_es`/`en_to_es`/`es_to_en`) to preview the art. |
| `$vocatchadmin stats` | Active card count + configured channels and their modes. |

## `$wcbetadmin` (group, owner-only)

World Cup betting admin. See [`cogs/wcbet.md`](./cogs/wcbet.md) for the
full feature.

| Subcommand | Description |
|-----------|-------------|
| `$wcbetadmin result <match_id> <score> [pens home\|away]` | Record a final score (e.g. `$wcbetadmin result 1 2-1`; also accepts `2:1` / `2 1`). Derives the outcome via `settle_outcome`, settles every pending bet on the match atomically (winners credited `floor(stake × odds)`), and posts a summary to `#world-cup-log`. Rejects duplicates. Works for group-stage and **resolved** knockout fixtures (set knockout teams first with `setteam`). **Knockouts can't draw** — on a level score, name the side that advanced on penalties with a trailing `pens home` / `pens away` (e.g. `$wcbetadmin result 73 1-1 pens home`); omitting it on a level knockout score is rejected with a hint. |
| `$wcbetadmin void <match_id>` | Refund all pending stakes on a match and mark the bets void (postponements/abandonments). |
| `$wcbetadmin stats` | Wallet count, pending bets, total coins staked, top balance. |
| `$wcbetadmin multiplier [value]` | Show or set the house odds multiplier applied to all offered lines (real ESPN lines **and** the flat fallback). No arg shows the current value; `$wcbetadmin multiplier 1.5` juices every price 1.5x; `1` resets to no boost. Allowed range 0.5–10. Affects **new** bets only — already-placed bets keep their snapshotted odds. |
| `$wcbetadmin setteam <match_id> <home> vs <away> [@ HH:MM]` | Resolve a knockout fixture's real teams (and optionally override the ET kickoff). Knockout fixtures ship with bracket placeholders and aren't bettable/settleable until resolved. Applies immediately (no redeploy) and persists in `wc_fixture_overrides`. Use exact team names as they appear in the standings, e.g. `$wcbetadmin setteam 73 Mexico vs Brazil` or `$wcbetadmin setteam 89 Spain vs France @ 16:00`. |
| `$wcbettest` | Owner-only test entrypoint for the user flow, retained alongside the public `$wcbet` (defined in `main.py`, not part of this group). |

## `$wcbetmod` (group, `manage_messages`)

Moderator tier for World Cup betting — per-user tools, a step below the
owner-only `$wcbetadmin` (which owns match-wide settlement). All actions
log to `#world-cup-log`. See [`cogs/wcbet.md`](./cogs/wcbet.md).

| Subcommand | Description |
|-----------|-------------|
| `$wcbetmod user <@user>` | Read-only summary: balance, pending bets/stake, lifetime won/lost/void, ban status. |
| `$wcbetmod ban <@user> [reason]` | Ban a user from opening the betting panel. |
| `$wcbetmod unban <@user>` | Lift a betting ban. |
| `$wcbetmod give <@user> <amount>` | Grant coins (confirmation prompt + loud log). Capped at 1,000,000 per action. |
| `$wcbetmod take <@user> <amount>` | Deduct coins (confirmation prompt + loud log); balance clamps at 0. |

## Owner-only utilities

See [`cogs/admin.md`](./cogs/admin.md), [`cogs/database.md`](./cogs/database.md), [`cogs/relay.md`](./cogs/relay.md), and [`cogs/tickets.md`](./cogs/tickets.md) for full details.

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$ask <question>` | Ask Gemini anything. | Owner-only |
| `$note <content>` / `$addnote` | Add a personal note to the database. | Owner-only |
| `$shownote <id>` / `$getnote` / `$readnote` | View a note by ID. | Owner-only |
| `$notes [limit]` / `$mynotes` / `$listnotes` | List your recent notes (default 5, max 20). | Owner-only |
| `$deletenote <id>` / `$delnote` / `$removenote` | Delete a note you own. | Owner-only |
| `$parrot [guild_id] [channel_id] <message>` | Relay a message to another guild/channel. | Owner-only |
| `$fetch [#channel] [count]` | Export messages as markdown (default 50, max 500). In a thread with no args, exports all. | Owner-only |
| `$fetchrange <start_link> <end_link>` / `$fetchr` | Export messages between two links (max 1000). | Owner-only |
| `$rawembed <message_link>` | Show raw embed JSON from a message. | Owner-only |
| `$sync [guild_id]` | Sync slash commands globally or to a guild. | Owner-only |
| `$mystats` | List all guilds the bot is in, sorted by member count. | Owner-only |
| `$leave <guild_id>` | Leave a guild by ID. | Owner-only |
| `$vcenrich <message_link>` | Parse a Rai voice-join log and render with avatars. | `manage_messages` |
| **VC Enrich** (context menu) | Right-click a Rai voice log, select "VC Enrich" → posts to enrich channel. | `manage_messages` |
| `$tickets` | Show open tickets across forum channels. | `manage_messages` |
| `$ticketsub` | Toggle new-ticket ping subscription. | `manage_messages` |
| `$summarize <start_link> <end_link> [topic]` / `$sum` | Summarize a conversation with Gemini (max 500 messages). | `manage_messages` |

## Permission model

- `@commands.is_owner()` is the default gate for admin commands —
  checks against `BOT_OWNER_ID` from env.
- A few commands use `@commands.has_permissions(manage_messages=True)`
  for mods (e.g. `$langexremove`, `$introtracker`).
- Slash-command equivalents of admin commands are rare; most admin
  tooling stays prefix-based.
