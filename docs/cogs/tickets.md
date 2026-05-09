# Tickets (`tickets_cog`)

Quick overview of open moderation tickets across forum channels.

## Overview

The tickets cog provides a single command (`$tickets`) that fetches all
open threads from configured forum channels and displays them in a
Components V2 layout view. Useful for moderators to see what needs
attention without clicking through each forum.

Threads are considered "open" if they have at least one tag matching the
configured `OPEN_TAGS` list (e.g., "open", "needs response"). Threads
with names in `FILTERED_THREADS` are always excluded.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$tickets` | Show open tickets across forum channels (staff + admin). Displays thread name, tags, response status (✅ = responded, ⏳ = awaiting response), and last interaction timestamp. | `manage_messages` |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `STAFF_FORUM_ID` | `cogs/tickets_cog/config.py` | 0 | Forum channel ID for staff tickets. |
| `ADMIN_FORUM_ID` | `cogs/tickets_cog/config.py` | 0 | Forum channel ID for admin tickets. |
| `OPEN_TAGS` | `cogs/tickets_cog/config.py` | `["open"]` | Tag names that mark a thread as "open". |
| `FILTERED_THREADS` | `cogs/tickets_cog/config.py` | `{"solved", "closed"}` | Thread names to always exclude. |

## Implementation notes

- The command posts a loading view first (`_loading_view`), then fetches
  threads and edits the message with the final view (`_tickets_view`).
- For each thread, the cog checks if there's been a response
  (`message_count > 1`) and fetches the last message to show the
  timestamp + author.
- If a forum channel is not configured (ID is 0), it's skipped.

> TODO: Add environment variable overrides for `STAFF_FORUM_ID` /
> `ADMIN_FORUM_ID` once forum channels are stable.
