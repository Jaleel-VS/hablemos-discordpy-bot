# Introduce (`introduce_cog`)

Multi-step introduction and language-exchange partner matching flow.

## Overview

The introduce cog lets members create two types of posts:

1. **Simple introduction**: Short bio + interests, posted publicly.
2. **Exchange partner post**: Detailed profile including languages
   offered/sought, proficiency level, region, and contact preferences.
   Posted publicly with a unique color based on native-language roles.

The flow is entirely modal/select-based (ephemeral interactions), with
all data validated before posting. Posts are tracked in the database to
enable cooldowns, repost logic, and self-service deletion.

Key features:

- **Bilingual UI**: Detects user's native language (Spanish vs. English)
  and shows prompts in that language. Falls back to English for "Other
  Native" users.
- **URL filtering**: Rejects any submission containing URLs or markdown
  links to prevent spam.
- **Repost cooldown**: 14-day cooldown on reposts, with a 10-minute
  grace period for immediate fixes after posting.
- **Self-service management**: Users can delete or repost their own
  exchange posts via `/exchange delete` and `/exchange repost`.
- **Color-coded embeds**: Exchange posts use different colors based on
  the user's native-language role combo (blue for English native, green
  for Spanish native, orange for both, purple for Other).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/introduce` | Start the introduction flow (modal-based). Must be used in the configured command channel. | None | None |
| `$introduce` | Post a persistent "Introduce Yourself" button in the current channel (typically the command channel). | None | 60s/channel |
| `/exchange delete` | Delete your own exchange-partner post (both DB row and message). | None | None |
| `/exchange repost` | Repost your exchange post. Subject to 14-day cooldown (or 10-minute grace period). | None | None |

The `/introduce` slash command is global; the `$introduce` prefix
command is available server-wide but typically used by staff to place
the persistent button.

### Admin commands

None. All management is self-service or happens via audit logs (see
[Audit logging](#audit-logging) below).

## Listeners & flows

### Multi-step interaction flow

1. **Entry**: User clicks the persistent "Introduce Yourself" button or
   runs `/introduce` in the command channel.
2. **`IntroStartView`**: "Are you looking for an exchange partner?"
   (Yes/No select + Continue button).
3. **Branch**:
   - **No (intro only)**: Opens `IntroOnlyModal` → two text fields
     (About Me, Interests) → validates, builds simple embed, posts to
     introductions channel.
   - **Yes (exchange partner)**: Opens `ExchangePrefsView` → four
     selects (offer language, seek language, level, region) → validates
     selections → opens `ExchangeDetailsModal` → four text fields (About
     Me, What I'm Looking For, Country, Other Language) → validates,
     builds detailed embed, posts to introductions channel, saves to
     `exchange_posts` table.

### Persistent button

`IntroduceButton` view with custom ID `introduce:start`, `timeout=None`,
registered once in `__init__`. Clicks survive restarts.

### Audit logging

All posts (intro-only and exchange) trigger an audit log message in the
configured `AUDIT_CHANNEL_ID` with jump link, user mention, and post
type. Deletion and repost also log.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `introductions` | `IntroductionsMixin` | One row per user who has ever used `/introduce`. Tracks `created_at`, `updated_at`. Currently minimal; primarily for historical tracking. |
| `exchange_posts` | `ExchangePostsMixin` | Active exchange posts (one per user). Columns: `user_id`, `channel_id`, `message_id`, `posted_at`, `data` (JSONB with full post content). Deleted when user runs `/exchange delete`. |

See [`../database.md`](../database.md) for query methods (in
`IntroductionsMixin` and `ExchangePostsMixin`).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `COMMAND_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where `/introduce` must be used. |
| `INTRODUCTIONS_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where intro/exchange posts are sent. |
| `AUDIT_CHANNEL_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Channel where audit logs are posted. |
| `SPANISH_NATIVE_ROLE_ID` / `ENGLISH_NATIVE_ROLE_ID` / `OTHER_NATIVE_ROLE_ID` | `cogs/introduce_cog/config.py` | (baked-in) | Used for UI language detection and embed color. |
| `REPOST_GRACE_MINUTES` | `cogs/introduce_cog/config.py` | 10 | Grace period after posting during which repost is allowed. |
| `REPOST_COOLDOWN_DAYS` | `cogs/introduce_cog/config.py` | 14 | Minimum days between reposts (outside grace period). |
| `OFFER_LANGUAGES` | `cogs/introduce_cog/config.py` | `[English, Spanish, Other]` | Languages you can offer (teach). |
| `SEEK_LANGUAGES` | `cogs/introduce_cog/config.py` | `[English, Spanish]` | Languages you can seek (learn). |
| `PROFICIENCY_LEVELS` | `cogs/introduce_cog/config.py` | `[A1..C2]` | CEFR proficiency levels for target language. |
| `REGIONS` | `cogs/introduce_cog/config.py` | List of 10 global regions | Broad regions for user location. |

All IDs accept environment variable overrides via `get_int_env` (from
root `config.py`).

## Persistent views

- **`IntroduceButton`**: Custom ID `introduce:start`. Registered once in
  `__init__` via `bot.add_view(...)` with `timeout=None`. Survives
  restarts. Kicks off the introduction flow.

## Known edge cases & gotchas

- **Command channel enforcement**: The `/introduce` slash command checks
  `interaction.channel_id == COMMAND_CHANNEL_ID` and rejects with an
  ephemeral message if used elsewhere. This keeps intro posts
  consolidated. The persistent button can be placed anywhere (typically
  also in the command channel).
- **One exchange post per user**: The flow blocks users who already have
  an active exchange post (`exchange_posts` row exists). They must
  delete or repost (which replaces) rather than creating a second post.
  Intro-only posts (no exchange partner) do not block this.
- **Repost vs. delete**: "Repost" deletes the old message, deletes the
  old DB row, creates a new message, and inserts a new DB row. It's
  effectively delete + create. The cooldown is checked against the old
  row's `posted_at`.
- **URL filtering**: The regex `_URL_RE` in `modals.py` catches
  `https?://`, `www.`, and markdown links `[text](url)`. Submissions
  containing any of these are rejected with an error. This is a simple
  spam-prevention measure; legitimate posts shouldn't need links.
- **Language detection**: `detect_ui_lang(member)` returns `"es"` if the
  user has the Spanish Native role *and not* the English Native role;
  otherwise `"en"`. This means dual-natives and "Other Native" users see
  English UI. The i18n module (`i18n.py`) stores bilingual strings for
  all prompts/labels/errors.
- **Embed color**: Exchange posts use `embed_color_for_member(member)`,
  which checks role combos. If the user has multiple native roles
  (English + Spanish), the color is orange. If they later remove a role,
  the embed color doesn't update (it's a static posted message). This is
  cosmetic and not worth re-rendering.
- **Audit channel**: If `AUDIT_CHANNEL_ID` is unavailable (channel
  deleted, bot lacks permissions), audit logging fails silently and logs
  an error server-side. The user's intro/exchange post still succeeds.
- **Modal timeouts**: Both `IntroStartView` and `ExchangePrefsView` have
  5-minute timeouts (`timeout=300`). If the user idles, the view expires
  and they must restart. Modals themselves have no timeout (they're
  instant once opened).

## Testing & debugging

- **Check DB state**: Query `exchange_posts` to see active posts.
  `data` is a JSONB column with the full embed content — useful for
  debugging reposts or inspecting old post data.
- **Repost cooldown edge case**: The grace period (`REPOST_GRACE_MINUTES
  = 10`) allows immediate reposts for typo fixes. To test, post an
  exchange, immediately run `/exchange repost`, and verify success. Wait
  11 minutes, try again, and verify it's blocked until 14 days pass.
- **Bilingual testing**: Create a test user with only the Spanish Native
  role and verify the UI strings are in Spanish. Create another with
  English Native and verify English. Test "Other Native" to ensure it
  falls back to English.
- **URL rejection**: Try submitting an intro with `https://example.com`
  or `[link](https://example.com)` in any text field and verify the
  error message.

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [`../database.md`](../database.md) — schema details.
- [`../architecture.md`](../architecture.md) — persistent views, modal
  patterns.
- [`./league.md`](./league.md) — another feature with persistent buttons
  and role validation.
