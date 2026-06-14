# Introduce (`introduce_cog`)

Simple member introductions via a modal flow.

> **Language exchange moved out.** Finding exchange partners now lives in
> [`langex.md`](./langex.md). This cog is introductions only.

## Overview

Members introduce themselves with a short bio + interests, posted
publicly to the introductions channel. The flow is a single modal
(ephemeral entry), with input validated before posting. Entry is via a
persistent "Introduce Yourself" button or the `/introduce` command.

Key features:

- **Bilingual UI**: detects the user's native language (Spanish vs.
  English) and shows prompts in that language; falls back to English.
- **URL filtering**: rejects submissions containing URLs or markdown
  links to prevent spam.
- **Color-coded embeds**: intro embeds use a neutral color; the
  `embed_color_for_member` helper (by native-language role) remains for
  shared use.

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/introduce` | Open the introduction modal. Must be used in the configured command channel. | None | None |
| `$introduce` | Post a persistent "Introduce Yourself" button in the current channel. | None | None |

## Listeners & flows

1. **Entry**: user clicks the persistent button or runs `/introduce` in
   the command channel.
2. **`IntroOnlyModal`** opens directly — two fields (About Me,
   Interests).
3. Validates (rejects URLs), builds a simple embed, posts to the
   introductions channel, records the introduction, and audit-logs.

### Persistent button

`IntroduceButton` view with custom ID `introduce:start`, `timeout=None`,
registered once in `__init__`. Clicks survive restarts.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `introductions` | `IntroductionsMixin` | One row per user who has used `/introduce`. Tracks `created_at`, `updated_at`. |

> `exchange_posts` is now owned by [`langex_cog`](./langex.md); this cog
> no longer reads or writes it.

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `COMMAND_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where `/introduce` must be used. |
| `INTRODUCTIONS_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where intro posts are sent. |
| `AUDIT_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where audit logs are posted. |
| `SPANISH_NATIVE_ROLE_ID` / `ENGLISH_NATIVE_ROLE_ID` / `OTHER_NATIVE_ROLE_ID` | `cogs/introduce_cog/config.py` | (baked-in) | UI language detection and embed color. |

## Persistent views

- **`IntroduceButton`**: Custom ID `introduce:start`, `timeout=None`,
  registered once. Survives restarts. Opens the introduction modal.

## Known edge cases & gotchas

- **Command channel enforcement**: `/introduce` checks
  `interaction.channel_id == COMMAND_CHANNEL_ID` and rejects elsewhere.
  The persistent button can be placed anywhere.
- **URL filtering**: the `_URL_RE` regex in `modals.py` catches
  `https?://`, `www.`, and markdown links. Submissions with any are
  rejected.
- **Language detection**: `detect_ui_lang(member)` returns `"es"` only
  for Spanish-native (and not English-native) members; everyone else
  sees English.

## Related

- [`langex.md`](./langex.md) — language-exchange partner finding (moved
  out of this cog).
- [`../commands.md`](../commands.md) — user command reference.
- [`../architecture.md`](../architecture.md) — persistent views, modals.
