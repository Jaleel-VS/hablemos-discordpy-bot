# Admin (`admin_cog`)

Owner-only cog management, metrics, server info, and utility commands.

## Overview

The admin cog is the bot owner's control panel. It provides:

- **Cog management**: Enable, disable, reload cogs at runtime.
- **Metrics**: View command usage statistics (daily, hourly, per-user).
- **Server info**: List guilds the bot is in, leave unwanted servers.
- **Message export**: Fetch and export message history as markdown.
- **Voice channel enrichment**: Parse Rai voice-join logs and render them
  with avatars.
- **Slash command sync**: Manually sync slash commands to Discord.
- **Daily cleanup task**: Rolls up old metrics and purges stale data.

All commands are owner-only (except where noted). Some utilities
(`$vcenrich`, `$fetch`, `$fetchrange`, `$rawembed`) allow `manage_messages`
users.

## Commands

### Cog management

| Command | Description |
|---------|-------------|
| `$cog list` | List all cogs and their status (loaded, disabled, unloaded, protected). |
| `$cog enable <name>` | Enable and load a cog (updates DB + loads extension). |
| `$cog disable <name>` | Disable and unload a cog (updates DB + unloads extension). Protected cogs cannot be disabled. |
| `$cog reload <name>` | Reload a cog (useful after code changes). |

> **Protected cogs**: `admin_cog` cannot be disabled (would lock you
> out). Add others to `PROTECTED_EXTENSIONS` if needed.

### Metrics

| Command | Description |
|---------|-------------|
| `$metrics [days]` | Show command usage summary (default 7 days, max 90). Total invocations, unique users, unique commands, error rate, top 10 commands. |
| `$metrics hours [days]` | Show usage by hour (UTC), rendered as a bar chart. |
| `$metrics user @someone [days]` | Show top commands for a specific user. |
| `$metrics retention` | Show table sizes (row counts) and retention policy. |
| `$metrics cleanup` | Manually trigger the daily cleanup task (rolls up metrics, purges old data). |

### Server info

| Command | Description |
|---------|-------------|
| `$mystats` | List all guilds the bot is in, sorted by member count. Shows join date. |
| `$leave <guild_id>` | Leave a guild by ID. |

### Message export

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$fetch [#channel] [count]` | Export the last N messages from a channel (default 50, max 500). In a thread with no args, exports all messages. Returns a markdown file. | Owner-only |
| `$fetchrange <start_link> <end_link>` / `$fetchr` | Export all messages between two message links (same channel). Max 1000 messages. Returns a markdown file. | Owner-only |

### Voice channel enrichment

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$vcenrich <message_link>` | Parse a Rai voice-join log embed and re-render it with participant avatars. Posts the enriched view in the current channel. | `manage_messages` |
| **VC Enrich** (context menu) | Right-click a Rai voice-join log message, select "VC Enrich" → posts to the configured enrich channel. | `manage_messages` |

### Utility

| Command | Description |
|---------|-------------|
| `$rawembed <message_link>` | Show the raw embed data from a message (JSON dict). Sends as file if too long. | Owner-only |
| `$sync [guild_id]` | Sync slash commands globally (no ID, takes up to 1 hour) or to a specific guild (instant). | Owner-only |

## Daily cleanup task

A `tasks.loop` runs every 24 hours (starts on bot ready):

1. **Roll up metrics**: Old rows from `command_metrics` (older than
   `METRICS_RETENTION_DAYS`, default 30) are aggregated into
   `metrics_daily` and deleted.
2. **Purge league activity**: Rows from `leaderboard_activity` for
   rounds older than the current round - 1 are deleted.

Metrics are rolled up by `(date, command_name)` with `MIN(cog_name)` to
avoid duplicate-key conflicts.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `command_metrics` | `MetricsMixin` | Raw command invocations. Retained for `METRICS_RETENTION_DAYS` days. |
| `metrics_daily` | `MetricsMixin` | Daily rollup of command usage (keyed on `date`, `command_name`). |

See [`../database.md`](../database.md) for query methods (in
`MetricsMixin`).

## Configuration

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `VC_ENRICH_CHANNEL_ID` | `cogs/admin_cog/config.py` | (baked-in) | Where the "VC Enrich" context menu posts results. |
| `METRICS_RETENTION_DAYS` | `cogs/admin_cog/main.py` | 30 | How long to keep raw `command_metrics` rows before rolling up. |
| `PROTECTED_EXTENSIONS` | `cogs/admin_cog/main.py` | `{'cogs.admin_cog.main'}` | Extensions that cannot be disabled. |

## Implementation notes

### Message export format

Both `$fetch` and `$fetchrange` produce markdown files with:

- Header (channel name, message count)
- Per-message: Jump link, timestamp, author, content, embeds (as JSON),
  attachments, stickers, reply references.
- Formatted for easy reading or further processing.

### Voice channel enrichment

Rai (a popular voice-tracking bot) logs voice joins with an embed
containing user IDs in a custom format. The `$vcenrich` command:

1. Parses the embed footer and field values with regex to extract user IDs.
2. Fetches `Member` objects (or falls back to "Unknown User" if fetch
   fails).
3. Builds a Components V2 layout view with avatars, display names,
   usernames, and user IDs.
4. Splits into multiple views if more than 10 participants (Discord's
   container limit).

The context menu variant posts to a dedicated channel for staff review.

### Slash command sync

`$sync` calls `bot.tree.sync()` with optional guild scoping. If a global
sync fails due to an Activity entry point conflict (Discord error
50240), the cog automatically falls back to guild-scoping for the
current guild.

## Known edge cases

- **Cog disable during runtime**: If you disable a cog and then try to
  run a command from it, the command won't exist (the cog is unloaded).
  Re-enable + reload to restore.
- **Metrics rollup conflicts**: The `MIN(cog_name)` trick in the daily
  rollup prevents upsert conflicts when a command is used in multiple
  cogs. See commit `4e0265e` for context.
- **Message export limits**: `$fetch` is capped at 500 messages per
  call. `$fetchrange` is capped at 1000 (Discord's history limit). For
  larger exports, run multiple fetches or use a dedicated archival tool.

## Related

- [`../admin.md`](../admin.md) — full admin command reference across all
  cogs.
- [`../architecture.md`](../architecture.md) — cog lifecycle, tasks.
- [`./error_handler.md`](./error_handler.md) — global error handling +
  metrics recording.
