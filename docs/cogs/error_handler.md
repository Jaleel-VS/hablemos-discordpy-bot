# Error Handler (`error_handler_cog`)

Global command error handler with friendly user messages and fuzzy
command suggestions.

## Overview

This cog listens to `on_command_error` and provides consistent,
user-friendly error messages for common failure modes:

- **Command not found**: Suggests similar commands via fuzzy matching
  (only in the main guild).
- **Cooldown**: Tells the user how long to wait.
- **Permission denied**: Shows a motivational quote + owner mention.
- **User input error**: Delegated to cog-level handlers (typically
  handled by `BaseCog.cog_command_error`).
- **Other errors**: Logs server-side, sends generic "try again later"
  message to user.

All failed commands are recorded to `command_metrics` with `failed=TRUE`.

## Configuration

No user-facing configuration. The cog reads `bot.settings.league_guild_id`
to determine the main guild for command-not-found suggestions.

## Implementation notes

- Fuzzy matching uses `difflib.get_close_matches` with a cutoff of 0.6.
  Up to 3 suggestions are shown.
- The cog checks `ctx.error_handled` to avoid double-handling if a
  cog-level or command-level handler already dealt with the error.
- `discord.Forbidden` errors are silently dropped (user likely blocked
  the bot).
- Permission-denied quotes are randomly selected from a hardcoded list
  of 30+ motivational quotes.

## Error channel

If `bot.error_channel` is set, command-not-found errors are also logged
there with full context (user, channel, guild, message link). Useful for
debugging user confusion.

## Related

- [`../architecture.md`](../architecture.md) — error handling patterns.
- [`./admin.md`](./admin.md) — admin cog handles metrics and cleanup.
