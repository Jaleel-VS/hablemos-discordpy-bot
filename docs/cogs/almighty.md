# Almighty (`almighty_cog`)

> **Working title** — name to be determined. This is a test feature.

Relays form submissions from one channel to another: a persistent button
in the trigger channel opens a form, and submissions are posted as embeds
in the feed channel. Write in one channel, read in another.

## Overview

A persistent panel with two buttons is posted once in the trigger
channel:

- **Submit** opens a free-text modal (Subject + Details).
- **Categorize** opens a modal with a single-choice radio group
  (Question / Idea / Bug / Other) plus an optional note.

Either modal formats the input into an embed — attributed to the
submitter — and posts it to the feed channel; the submitter gets an
ephemeral confirmation.

The buttons survive bot restarts (`timeout=None` + stable `custom_id`,
registered via `bot.add_view`), so they keep working without re-posting.
The forms are intentionally minimal; this is the skeleton for a richer
submission flow later. The Categorize form demonstrates the Components
V2 `RadioGroup` (a modal-scoped, single-choice picker wrapped in a
`Label`).

## Commands

### Admin commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$almightypanel` | Post the persistent submission panel (both buttons) into the trigger channel. | `manage_guild` |

## Listeners & flows

No `on_message` listeners. The flow is button-driven:

1. Admin runs `$almightypanel` → the persistent panel (**Submit** +
   **Categorize**) is posted in the trigger channel.
2. A member presses a button → the matching modal opens
   (`SubmissionModal` or `CategoryModal`).
3. Member fills the form and submits.
4. `on_submit` builds an embed and the shared `_relay_to_feed` helper
   posts it to the feed channel.
5. The member receives an ephemeral "✅ Submitted!" confirmation.

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `ALMIGHTY_TRIGGER_CHANNEL_ID` | `cogs/almighty_cog/config.py` | (baked-in) | Channel hosting the persistent Submit button. |
| `ALMIGHTY_FEED_CHANNEL_ID` | `cogs/almighty_cog/config.py` | (baked-in) | Channel where submissions are posted. |
| `CATEGORIES` | `cogs/almighty_cog/config.py` | 4 entries | (label, description) options for the radio group; 2–10 entries. |

## Persistent views

- **TriggerView**: two buttons with custom IDs `almighty:submit`
  (opens `SubmissionModal`) and `almighty:categorize` (opens
  `CategoryModal`).
  Registered once in `__init__` via `bot.add_view(...)`, guarded against
  duplicate registration on cog reload.

## Known edge cases & gotchas

- **Slow/failed feed post**: the shared `_relay_to_feed` helper
  acknowledges the interaction *first* (ephemeral "⏳ Submitting…") so the
  modal always closes within Discord's 3-second window, then edits that
  message to the final result (✅ or an error). This avoids a "This
  interaction failed" if the feed send is slow or rate-limited.
- **Missing/forbidden feed channel**: if the feed channel is unavailable
  or the bot lacks permission to post there, the submitter sees an
  ephemeral error (logged server-side) and the submission is dropped.
- **Unexpected errors**: the modals share a `_RelayModal.on_error`
  backstop that acknowledges the interaction on any unhandled exception,
  so the modal never hangs open silently.
- **RadioGroup is modal-scoped**: it's a Components V2 modal item
  (`is_dispatchable()` is False), read via `.value` in `on_submit` — not
  a message component. It must be wrapped in a `Label` and allows 2–10
  options.
- **No persistence of submissions**: submissions live only as messages
  in the feed channel — there's no DB record yet. Add a table if history
  or editing is needed later.

## Related

- [`admin.md`](../admin.md) — admin command reference.
- [`architecture.md`](../architecture.md) — cog loading and persistent
  views.
