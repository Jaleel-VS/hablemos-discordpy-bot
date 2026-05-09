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
| `$league topchannels [days]` (alias: `topchans`) | Top 15 channels by counted-message volume over a window. Flags excluded channels with 🚫. |
| `$league heatmap [days]` (alias: `hm`) | 7×24 day-of-week × hour activity heatmap rendered with block-shading. UTC. |

## Crossword admin (owner-only)

Defined directly in `crossword_cog/main.py`. See
[`cogs/crossword.md`](./cogs/crossword.md) for the feature.

| Command | Description |
|---------|-------------|
| `$cwtimeout <seconds>` | Override the crossword timeout for the remaining lifetime of the bot process. Useful for testing. |
| `$cwstats [days\|all]` | Aggregate crossword stats: games, participants, completion breakdown (completed/timeout/quit/interrupted), hints usage, top solvers. |
| `$cwwords <hardest\|easiest\|unseen> [lang] [limit]` | Per-word solve-rate analysis. `unseen` requires a language; others filter optionally. |

## Other cogs

> TODO: enumerate admin commands for:
> `admin_cog`, `database_cog`, `error_handler_cog`, `interactions_cog`,
> `relay_cog`, `summary_cog`, `tickets_cog`, `website_manager_cog`.

## Permission model

- `@commands.is_owner()` is the default gate for admin commands —
  checks against `BOT_OWNER_ID` from env.
- A few commands use `@commands.has_permissions(manage_messages=True)`
  for mods (e.g. `/exchange remove`, `$exchangereset`).
- Slash-command equivalents of admin commands are rare; most admin
  tooling stays prefix-based.
