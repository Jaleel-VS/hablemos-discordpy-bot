# Language Exchange (`langex_cog`)

Find a language-exchange partner — a Discord pen pal in your target
language — with structured profiles and mutual-match suggestions.

## Overview

A persistent panel in the language-exchange channel offers three
buttons:

- **Post / update profile** — an ephemeral select step (language you
  speak, language you want to learn, your level, region) followed by a
  short details modal (about you, what you're looking for, interests).
  Posts a **Components V2 profile card** to the feed channel and stores
  the structured data.
- **Find a partner** — ranks people who are a *mutual* match for you and
  shows up to 10, each with a jump link to their post. Ephemeral.
- **Delete my profile** — removes your posted message and your record.

This cog replaces the legacy free-text `#language-exchange` channel and
is separate from introductions ([`introduce.md`](./introduce.md)). It
reuses the shared `exchange_posts` table, so there is one live profile
per user (re-posting replaces the old message).

The matching engine ([`cogs/langex_cog/matching.py`]) is pure (no
Discord/DB deps) and unit-tested.

## Commands

### User-facing

All user interaction is through the persistent panel buttons (no slash
commands). The panel is placed once by an admin.

### Admin commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$langexpanel` | Post the persistent panel (Post / Find / Delete) into the langex channel. | `manage_guild` |
| `$langexremove <user>` | Remove a user's profile (message + record). | `manage_messages` |

## Listeners & flows

No `on_message` listeners — entirely button/modal driven.

### Post / update

1. **Post / update profile** → ephemeral `PrefsView`: four selects
   (speak / learn / level / region).
2. Validates (all chosen; speak ≠ learn) → opens `DetailsModal`
   (about / looking-for / interests; rejects URLs).
3. Acknowledges first (ephemeral), deletes any previous profile message,
   posts the new embed to the feed channel, upserts `exchange_posts`,
   then edits the ephemeral to a confirmation.

### Find a partner

1. **Find a partner** → loads your profile (nudges you to post first if
   you have none).
2. Loads all profiles, runs `matching.rank_matches`, shows up to 10.

### Match scoring

A match is **reciprocal**: you offer the language they want to learn,
**and** they offer the language you want to learn. Among reciprocal
candidates, the score adds:

- **Region** — +3 same region, +1 same hemisphere bucket.
- **Shared interests** — +1 per overlapping keyword (from the free-text
  fields), capped at +4.
- **Level fit** — +2 when target levels are within one CEFR step.
- **Recency** — +2 posted within 7 days, +1 within 30 days (favors
  active users).

Ties break by most-recent post, then user ID (stable ordering).

## Posted profile card (Components V2)

Profiles are posted as a `LayoutView` (not a flat embed):

- a `Container` with a native-language accent color,
- a `Section` with the header (name, speaks/learning/level, region) and
  the user's **avatar as a thumbnail accessory**,
- `TextDisplay` blocks for About / Looking for / Interests,
- a footer `Section` with the poster's **mention** and a **📩 Contact**
  button accessory.

The Contact button is a `discord.ui.DynamicItem` whose `custom_id`
encodes the poster's user id (`langex:contact:<user_id>`), so it works on
every profile message and survives restarts without tracking each
message. Pressing it posts a public in-channel message pinging both the
presser and the poster to kick off the exchange (a presser can't contact
their own profile).

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `exchange_posts` | `ExchangePostsMixin` | One active profile per user: `user_id`, `message_id`, `channel_id`, `posted_at`, `post_data` (JSONB with offer/seek language, level, region, DM preference, about/looking-for/interests text). |

`get_all_exchange_posts()` returns every row for the matcher. See
[`../database.md`](../database.md).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `LANGEX_PANEL_CHANNEL_ID` | `cogs/langex_cog/config.py` | (baked-in) | Channel hosting the persistent panel. |
| `LANGEX_FEED_CHANNEL_ID` | `cogs/langex_cog/config.py` | (= panel channel) | Channel where profile embeds are posted. |
| `LANGEX_AUDIT_CHANNEL_ID` | `cogs/langex_cog/config.py` | (baked-in) | Audit-log channel. |
| `SPANISH_NATIVE_ROLE_ID` / `ENGLISH_NATIVE_ROLE_ID` / `OTHER_NATIVE_ROLE_ID` | `cogs/langex_cog/config.py` | (baked-in) | Bilingual UI + embed color. |
| `OFFER_LANGUAGES` / `SEEK_LANGUAGES` / `PROFICIENCY_LEVELS` / `REGIONS` / `DM_OPTIONS` | `cogs/langex_cog/config.py` | sensible defaults | Profile option lists. |

## Persistent views

- **`LangExPanelView`**: three buttons with custom IDs `langex:post`,
  `langex:find`, `langex:delete`. Registered once in `__init__` via
  `bot.add_view(...)`, guarded against duplicate registration.
- **`ContactButton`** (`DynamicItem`, template
  `langex:contact:(?P<user_id>\d+)`): the per-profile Contact button.
  Registered once via `bot.add_dynamic_items(ContactButton)`.

## Known edge cases & gotchas

- **One profile per user**: re-posting via **Post / update** deletes the
  old message and replaces it; there's only ever one live profile.
- **Reciprocity required**: Find returns only mutual matches. Someone who
  offers what you seek but doesn't want what you offer won't appear — by
  design (the point is a fair 50/50 exchange).
- **Region as timezone proxy**: timezone isn't captured structurally;
  region proximity stands in for "nearby/overlapping hours."
- **Interests are free text**: matching does lightweight keyword overlap
  on the about/looking-for/interests fields, not a structured tag list.
- **5-row modal/view limit**: the prefs step uses four selects + one
  button (the limit). DM preference currently defaults to "DM me"; add a
  structured field only if you free up a row.
- **Slow/failed feed post**: `DetailsModal` acknowledges first, then
  posts, then edits the ephemeral — so the modal always closes within
  Discord's 3-second window. `on_error` is a backstop.
- **Shared table during transition**: `exchange_posts` is shared with the
  legacy data; the introduce cog no longer touches it.

## Testing & debugging

- `tests/langex/test_matching.py` covers the scoring engine (reciprocity,
  ranking, limits, edge cases) with no Discord/DB needed.
- Query `exchange_posts` to inspect live profiles; `post_data` is JSONB
  with the full structured profile.

## Related

- [`introduce.md`](./introduce.md) — introductions (now separate).
- [`admin.md`](../admin.md) — admin command reference.
- [`../database.md`](../database.md) — schema details.
- [`../architecture.md`](../architecture.md) — persistent views, modals.
