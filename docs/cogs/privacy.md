# Privacy (`privacy_cog`)

Self-serve deletion of everything the bot stores about a member.

## Overview

`/deletemydata` (also `$deletemydata`) shows what will be deleted and what
is kept, then waits for the member to press **Delete my data**. Deletion
runs in one database transaction, so it either completes or changes
nothing. The reply says how many records were removed.

The bot owner can run the same deletion for a user ID with `$purgeuser`,
for requests that come through moderators (for example, from someone who
has left the server).

This cog backs the deletion answer in Discord's privileged intent review
and the "Removing your data" section of [`PRIVACY.md`](../../PRIVACY.md).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/deletemydata` / `$deletemydata` | Delete everything stored about you, after a confirmation button. The slash version replies ephemerally. | None | 60s/user |

### Admin commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$purgeuser <user_id>` | Delete everything stored about a user ID, after a confirmation button. | Owner-only |

## What is deleted and what is kept

`db/privacy.py` is the source of truth:

- **Deleted:** notes, vocab notes, practice progress, League standings and
  activity, round wins, command metrics, interaction records (both sides),
  crossword and dictation scores, vocab-card catches, ticket subscriptions,
  message counts, activity first/last seen, clock and Spotify settings,
  World Cup predictions and bets, and the Activity service's game results,
  stats, sessions and pets.
- **Anonymized:** crossword word events (`solved_by` set to `NULL`). A
  League-banned member keeps their `leaderboard_users` row so the ban
  survives, with the username cleared and `opted_in` set to false.
- **Kept** (`KEPT_TABLES`): the quote opt-out, moderation records (quote
  bans, no-GIF restrictions, betting bans, intro exemptions, intro
  history), anti-spam cooldowns (exchange posts), champion-role
  bookkeeping, and the staff task board. Deleting data must not lift a ban
  or undo an opt-out.

`tests/test_privacy.py` parses `db/schema.py` and
`activity/backend/app/db.py` and fails if a table with a `user_id`
(or `user_a`, `user_b`, `solved_by`) column is in neither list. When you
add a per-user table, add it to `db/privacy.py` in the same commit.

## Listeners & flows

After a successful deletion the view dispatches `user_data_deleted` with
the user ID. Cogs that cache per-user state listen for it:

- `league_cog` drops the member from its opted-in, learning-language and
  daily-count caches, so it stops counting their messages straight away.

Add a listener to any new cog that caches per-user data in memory.

## Related

- [`../database.md`](../database.md) — table ownership.
- [`../../PRIVACY.md`](../../PRIVACY.md) — the public privacy policy.
