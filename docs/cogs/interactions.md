# Interactions (`interactions_cog`)

Track and analyze reply/mention interactions between users.

## Overview

The interactions cog listens to all messages and records when users
reply to or mention each other. It provides commands to visualize these
interactions as "top pairs" (who interacts with whom most often) and
individual interaction logs.

Data is retained for a configurable period (default 90 days) and purged
daily. All tracking is automatic; no user action required.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$interactions [#channel] [duration]` | Show top reply/mention pairs in a channel over a time window. Examples: `$interactions`, `$interactions 12h`, `$interactions #general 3d`. | None | 60s/channel |
| `$interactionlog [@user] [duration]` | Show interactions by/with a user (who they've replied to/mentioned, who's replied to/mentioned them). Example: `$interactionlog @someone 7d`. | None | 60s/channel |

## Listeners

### `on_message` → interaction recording

For every message in a guild:

1. **Reply tracking**: If the message is a reply to a non-bot user
   (other than the author), record a `reply` interaction.
2. **Mention tracking**: For each mentioned non-bot user (other than the
   author and the reply target), record a `mention` interaction.

Interactions are written to `interactions` table with `(channel_id,
guild_id, author_id, target_id, kind, timestamp)`.

## Daily purge task

A `tasks.loop` runs every 24 hours (starts on bot ready) and deletes
rows older than `INTERACTIONS_RETENTION_DAYS` (default 90).

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `interactions` | `InteractionsMixin` | One row per reply/mention event. Columns: `channel_id`, `guild_id`, `author_id`, `target_id`, `kind` (`reply` or `mention`), `created_at` (TIMESTAMPTZ). |

See [`../database.md`](../database.md) for query methods (in
`InteractionsMixin`).

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `INTERACTIONS_RETENTION_DAYS` | `cogs/interactions_cog/config.py` | 90 | How long to keep interaction rows before purging. |

## Implementation notes

- The cog uses a `VisibilityView` (from `cogs/utils/visibility.py`) to
  let users toggle between public and ephemeral visibility for results.
- Duration parsing supports human-friendly strings like `7d`, `1d12h`,
  `30m` (see `cogs/utils/duration.py`).
- The cog suppresses repeated DB errors to avoid log spam — if recording
  fails 3 times, further errors are muted until success.

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [`./league.md`](./league.md) — another feature with real-time message
  tracking.
