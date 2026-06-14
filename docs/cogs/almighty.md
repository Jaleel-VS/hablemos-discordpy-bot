# Almighty (`almighty_cog`)

> **Working title** — name to be determined. This is a test feature.

Relays form submissions from one channel to another: a persistent button
in the trigger channel opens a form, and submissions are posted as embeds
in the feed channel. Write in one channel, read in another.

## Overview

A persistent "Submit" button is posted once in the trigger channel.
Pressing it opens a modal with two fields (Subject, Details). On submit,
the contents are formatted into an embed — attributed to the submitter —
and posted to the feed channel. The submitter gets an ephemeral
confirmation.

The button survives bot restarts (`timeout=None` + stable `custom_id`,
registered via `bot.add_view`), so it keeps working without re-posting.
The current form is intentionally minimal; it's the skeleton for a
richer submission flow later.

## Commands

### Admin commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$almightypanel` | Post the persistent submission button into the trigger channel. | `manage_guild` |

## Listeners & flows

No `on_message` listeners. The flow is button-driven:

1. Admin runs `$almightypanel` → the persistent **Submit** button is
   posted in the trigger channel.
2. A member presses **Submit** → `SubmissionModal` opens.
3. Member fills Subject + Details and submits.
4. `on_submit` builds an embed and posts it to the feed channel.
5. The member receives an ephemeral "✅ Submitted!" confirmation.

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `ALMIGHTY_TRIGGER_CHANNEL_ID` | `cogs/almighty_cog/config.py` | (baked-in) | Channel hosting the persistent Submit button. |
| `ALMIGHTY_FEED_CHANNEL_ID` | `cogs/almighty_cog/config.py` | (baked-in) | Channel where submissions are posted. |

## Persistent views

- **TriggerView**: Custom ID `almighty:submit`. Opens `SubmissionModal`.
  Registered once in `__init__` via `bot.add_view(...)`, guarded against
  duplicate registration on cog reload.

## Known edge cases & gotchas

- **Missing/forbidden feed channel**: if the feed channel is unavailable
  or the bot lacks permission to post there, the submitter gets an
  ephemeral error and the submission is dropped (logged server-side).
- **No persistence of submissions**: submissions live only as messages
  in the feed channel — there's no DB record yet. Add a table if history
  or editing is needed later.

## Related

- [`admin.md`](../admin.md) — admin command reference.
- [`architecture.md`](../architecture.md) — cog loading and persistent
  views.
