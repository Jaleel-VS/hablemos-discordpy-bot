# Wordle launcher (`wordle_cog`)

Gives players a discoverable way to open the Spanish Wordle
[Activity](../activity.md) without hunting the voice-channel Activity Shelf.

## Overview

Discord Activities normally launch from the 🚀 Activity Shelf, which most users
never find. `$wordle` posts a message with a button that launches the Activity
directly, using the `LAUNCH_ACTIVITY` interaction response (discord.py 2.6+
`interaction.response.launch_activity()`, callback type 12).

Discord opens the Activity in the channel the button was clicked from — servers
and DMs are both valid launch contexts, so no voice channel is required.

## Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `$wordle` / `$palabra` | Post an embed with a "Jugar Wordle" button. | 10s/user |

## Flow

1. User runs `$wordle`.
2. The bot posts an embed + a `LaunchView` button.
3. User clicks → the button callback calls `interaction.response.launch_activity()`.
4. Discord opens the app's Activity in the user's current voice channel.

## Known edge cases & gotchas

- **Launch failure**: if `launch_activity()` raises `HTTPException`, the
  callback catches it and replies (ephemerally) with a generic retry message.
  No voice channel is required — Activities launch in the channel/DM the button
  was clicked from.
- **Button timeout**: the view times out after 180s. It's an on-demand button
  meant to be clicked right away, so it is *not* a persistent view — re-run
  `$wordle` for a fresh one.
- **Activities must be enabled** on the app (they are) or the launch fails.

## Related

- [`../activity.md`](../activity.md) — the Activity itself (framework, Wordle, persistence).
- [`activity_results.md`](./activity_results.md) — how finished daily games post to a channel.
