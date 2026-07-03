# Tickets (`tickets_cog`)

Quick overview of open moderation tickets across forum channels.

## Overview

The tickets cog provides the `$tickets` command, which fetches all
open threads from configured forum channels and displays them in a
Components V2 layout view, plus an opt-in notification system
(`$ticketsub`) that pings subscribed moderators in a configured channel
whenever a new ticket is opened. Useful for moderators to see what needs
attention without clicking through each forum.

Threads are considered "open" if they have at least one tag matching the
configured `OPEN_TAGS` list (e.g., "open", "needs response"). Threads
with names in `FILTERED_THREADS` are always excluded.

New-ticket pings fire on `on_thread_create` for any thread opened in a
watched forum (excluding `FILTERED_THREADS`). The Open-tag filter is
*not* applied here because a freshly created thread may not have its tags
applied yet — every brand-new ticket is treated as unhandled.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$tickets` | Show open tickets across forum channels (staff + admin) in a paginated view (8 per page, ◀/▶ navigation). Displays thread name, tags, response status (✅ = responded, ⏳ = awaiting response), and last interaction timestamp. | `manage_messages` |
| `$ticketsub` | Toggle your subscription to new-ticket pings. Subscribed mods are mentioned in the notification channel when a new ticket is opened. Subscriptions persist in the `ticket_subscriptions` table. | `manage_messages` |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `STAFF_FORUM_ID` | `cogs/tickets_cog/config.py` | 0 | Forum channel ID for staff tickets. |
| `ADMIN_FORUM_ID` | `cogs/tickets_cog/config.py` | 0 | Forum channel ID for admin tickets. |
| `NOTIFY_CHANNEL_ID` | `cogs/tickets_cog/config.py` | `297877202538594304` | Channel where new-ticket pings are posted (env: `TICKETS_NOTIFY_CHANNEL_ID`). `0` disables the ping listener. |
| `OPEN_TAGS` | `cogs/tickets_cog/config.py` | `["open"]` | Tag names that mark a thread as "open". |
| `FILTERED_THREADS` | `cogs/tickets_cog/config.py` | `{"solved", "closed"}` | Thread names to always exclude. |

## Implementation notes

- The command posts a loading view first (`_loading_view`), then fetches
  threads and edits the message with the final paginated view
  (`TicketsView`). If no forum has open tickets it shows
  `_empty_tickets_view` instead.
- Open threads across all forums are flattened into one list of
  `(forum_label, line)` entries and paginated at `PAGE_SIZE` (8) per
  page, so a forum with many tickets is no longer silently truncated.
  `TicketsView` is invoker-locked (only the mod who ran `$tickets` can
  flip pages) and disables its ◀/▶ buttons on timeout. A forum spanning
  a page boundary re-emits its header at the top of the next page.
- For each thread, the cog checks if there's been a response
  (`message_count > 1`) and fetches the last message to show the
  timestamp + author.
- If a forum channel is not configured (ID is 0), it's skipped.
- `$ticketsub` toggles a row in `ticket_subscriptions` (PK `(user_id,
  guild_id)`). The `on_thread_create` listener loads subscribers for the
  thread's guild and sends one message mentioning all of them in
  `NOTIFY_CHANNEL_ID`, with `AllowedMentions(users=True)`.
- If `NOTIFY_CHANNEL_ID` is `0`, both the listener and `$ticketsub` are
  inert (the command tells the user notifications aren't configured).

> TODO: Add environment variable overrides for `STAFF_FORUM_ID` /
> `ADMIN_FORUM_ID` once forum channels are stable.
