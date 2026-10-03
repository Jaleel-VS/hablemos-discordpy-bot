# Error Handler (`error_handler_cog`)

Global catch-all for prefix-command errors that `BaseCog` does not
already answer.

## Overview

discord.py always runs `Cog.cog_command_error` first, then dispatches
`on_command_error`. Split of responsibility:

- **`BaseCog.cog_command_error`**: cooldown, check/permission failure
  (including `fail_msg` on the predicate), user-input/usage. Sets
  `ctx.error_handled`.
- **This cog**: `CommandNotFound` in the league guild (always replies;
  fuzzy suggestions when a close match exists), failed-command metrics,
  unexpected invoke errors. Skips anything already marked `error_handled`.

User-facing copy for expected failures lives in one place (`base_cog.py`).
Do not re-implement cooldown or permission replies in individual cogs.

All failed commands that reach this listener are recorded to
`command_metrics` with `failed=TRUE`.

## Configuration

No user-facing configuration. The cog reads `bot.settings.league_guild_id`
to determine the main guild for command-not-found suggestions.

## Implementation notes

- Fuzzy matching uses `difflib.get_close_matches` with a cutoff of 0.6.
  Up to 3 suggestions are shown. No match still gets a help-pointer reply.
- The cog checks `ctx.error_handled` to avoid double-handling if a
  cog-level or command-level handler already dealt with the error.
- Unexpected invoke errors log the traceback server-side and send a
  generic "try again later" reply. `discord.Forbidden` is dropped
  (user likely blocked the bot).

## Error channel

If `bot.error_channel` is set, command-not-found errors are also logged
there with full context (user, channel, guild, message link). Useful for
debugging user confusion.

## Related

- [`../architecture.md`](../architecture.md) — error handling patterns.
- [`./admin.md`](./admin.md) — admin cog handles metrics and cleanup.
