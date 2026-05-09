# [Cog Name] (`<feature>_cog`)

> **Template**: Copy this file to create new per-cog deep-dive docs.
> Delete sections that don't apply (e.g., if there are no persistent
> views, remove that section).

One-sentence summary of what this cog does and why it exists.

## Overview

2–3 paragraphs explaining the feature: what it enables, how users
interact with it, and what makes it different from similar features if
applicable.

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/foo` | Does X. Returns Y. | None | 10s/user |
| `$bar [arg]` | Does Z. Aliases: `$baz` | None | 30s/channel |

### Admin commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$fooadmin reset` | Clears all state. | Owner-only |

> If there are many admin commands, link to the admin section in
> [`../admin.md`](../admin.md) instead of duplicating here.

## Listeners & flows

Describe any `on_message`, `on_member_join`, or other event listeners
that drive behavior. Use sequence diagrams (text or mermaid) if the flow
is complex.

**Example:**

1. User types `!hint` in a crossword channel.
2. `on_message` checks if a game is active.
3. Reveals a random unrevealed cell, increments `hints_used`.
4. Re-renders the grid and edits the game message.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `foo_data` | `FooMixin` | One row per foo instance; tracks state X and Y. |
| `foo_events` | `FooMixin` | Time-series event log. |

Link to the relevant section of [`../database.md`](../database.md) if
the table is documented there.

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `FOO_CHANNEL_ID` | `cogs/foo_cog/config.py` | (baked-in) | Where foo messages are posted. |
| `FOO_API_KEY` | Root `config.py` | unset | Optional; enables feature X. |

## Persistent views

If the cog registers any `discord.ui.View` with `timeout=None`, describe
them here:

- **FooButton**: Custom ID `foo:button_action`. Kicks off the foo flow.
  Registered once in `__init__` via `bot.add_view(...)`.

## Known edge cases & gotchas

- **Concurrent games**: Only one game allowed per channel; second
  attempt is rejected with an error message.
- **Restart recovery**: Games interrupted by a bot restart are detected
  via `foo_active_games` and resumed on the next boot.
- **Rate limiting**: Uses the shared `RateLimiter` from
  `cogs/utils/rate_limiter.py` to avoid hitting the Foo API quota.

## Testing & debugging

Owner-only commands or environment tweaks useful for testing:

- `$footimeout <seconds>` — override the default timeout for the current
  process lifetime.
- Set `FOO_DEBUG=1` to enable verbose logging.

## Related

- [`commands.md`](../commands.md) — user command reference.
- [`admin.md`](../admin.md) — admin command reference.
- [`architecture.md`](../architecture.md) — how cogs load and interact
  with the DB.
- Other cog docs under [`./`](./) if this feature depends on or
  integrates with them.
