# Activity launchers (`wordle_cog`, `conjuga_cog`)

Give players a discoverable way to open the embedded [Activity](../activity.md)
without hunting the 🚀 Activity Shelf.

## Overview

Discord Activities normally launch from the Activity Shelf, which most users
never find. `$wordle` and `$conjuga` post a message with a button that launches
the Activity directly, using the `LAUNCH_ACTIVITY` interaction response
(discord.py 2.6+ `interaction.response.launch_activity()`, callback type 12).

Discord opens the Activity in the channel the button was clicked from — servers
and DMs are both valid launch contexts, so no voice channel is required.

The two launcher cogs share one implementation,
[`cogs/utils/activity_launch.py`](../../cogs/utils/activity_launch.py)
(`ActivityLaunchView`); each cog only supplies its button label/emoji and embed.

## Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `$wordle` / `$palabra` | Post an embed with a "Jugar Wordle" button. | 10s/user |
| `$conjuga` / `$conjugar` | Post an embed with a "Jugar Conjugación" button. | 10s/user |

## Flow

1. User runs the command.
2. The bot posts an embed + an `ActivityLaunchView` button.
3. User clicks → the button callback calls `interaction.response.launch_activity()`.
4. Discord opens the app's Activity in the channel the button was clicked from.

## One app, no deep-link

There is a single Activity (one app / one `client_id`), so **every** launcher
button opens the same app. The app decides what to show:

- **One game registered** → it boots straight into that game.
- **Two or more** → it shows the game **hub/menu**.

The `LAUNCH_ACTIVITY` callback carries **no deep-link parameter**, so a per-game
command cannot pre-select a game — `$wordle` and `$conjuga` are themed,
discoverable entry points that both land on the hub once multiple games exist.
This is a Discord platform constraint, not a bug. (The SDK's user-facing
`shareLink` does support custom query params, but that's for links a *user*
shares, not the bot's launch.)

## Known edge cases & gotchas

- **Launch failure**: if `launch_activity()` raises `HTTPException`, the shared
  view catches it and replies (ephemerally) with a generic retry message. No
  voice channel is required.
- **Button timeout**: the view times out after 180s. It's an on-demand button
  meant to be clicked right away, so it is *not* a persistent view — re-run the
  command for a fresh one.
- **Activities must be enabled** on the app (they are) or the launch fails.

## Related

- [`../activity.md`](../activity.md) — the Activity itself (framework, games, persistence).
- [`activity_results.md`](./activity_results.md) — how finished daily games post to a channel.
