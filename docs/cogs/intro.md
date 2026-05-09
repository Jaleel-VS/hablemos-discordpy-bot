# Intro (`intro_cog`)

Introduction tracker — enforces a cooldown on the introductions channel.

## Overview

The intro cog monitors a designated introductions channel and warns/
alerts when users post multiple times within a cooldown period (default
90 days). This prevents spam and ensures everyone gets a turn to
introduce themselves.

**Note**: This is separate from the `introduce_cog` (which handles the
multi-step intro/exchange flow). This cog is purely a **moderation tool**
for a traditional text-based introductions channel.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$introtracker add <channel_id>` | Track a channel for intro cooldown enforcement. | `manage_messages` |
| `$introtracker remove <channel_id>` | Stop tracking a channel. | `manage_messages` |
| `$introtracker list` | List all tracked channels. | `manage_messages` |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `INTRO_COOLDOWN_DAYS` | `cogs/intro_cog/config.py` | 90 | Minimum days between intro posts. |
| `DEFAULT_WARN_CHANNEL_ID` | `cogs/intro_cog/config.py` | (baked-in) | Where warnings are posted (visible to mods). |
| `DEFAULT_ALERT_CHANNEL_ID` | `cogs/intro_cog/config.py` | (baked-in) | Where alerts are posted (visible to all). |
| `EXEMPT_ROLE_IDS` | `cogs/intro_cog/config.py` | `[]` | Roles exempt from cooldown (e.g., bot owner, mods). |

## Behavior

On every message in a tracked channel:

1. Check if user has posted in this channel before (within cooldown).
2. If yes:
   - Post a **warning** in the warn channel (mod-only).
   - Post an **alert** in the alert channel (public reminder).
   - Track the second (or third, etc.) intro in the DB.
3. If no:
   - Record the first intro timestamp.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `introductions` | `IntroductionsMixin` | User intro records (one row per channel per user). Columns: `user_id`, `channel_id`, `created_at`, `updated_at`. |

See [`../database.md`](../database.md) for query methods (in
`IntroductionsMixin`).

## Related

- [`./introduce.md`](./introduce.md) — multi-step intro/exchange flow
  (different feature).
