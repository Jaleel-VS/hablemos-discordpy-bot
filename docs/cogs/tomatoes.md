# Tomatoes (`tomatoes_cog`)

Throw a tomato image at a mentioned user.

## Overview

`$tomato` renders a still WebP overlay. `$tomato2` (`$t2`) renders an
animated GIF. Both resolve the target the same way: a mention that
appears in the command text, otherwise the author of a replied-to
message.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$tomato [@user]` / `$tomatoes` | Still overlay. | None | 5s/user |
| `$tomato2 [@user]` / `$t2` | Animated GIF. | None | 5s/user |

## Implementation notes

- Target resolution is `_target_user` in `main.py`. Mentions that
  Discord attached from a reply but that are not in the typed command
  are ignored so a reply-only invoke hits the replied-to author.
- `$tomato` writes a temp WebP and deletes it in `finally`.
- `$tomato2` streams a GIF from memory via `generate_tomatoes_v2`.

## Related

- [`../commands.md`](../commands.md) — user command list.
