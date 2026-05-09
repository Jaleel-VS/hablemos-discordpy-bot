# Conversation Starter (`convo_starter_cog`)

Random bilingual discussion topics to spark conversations.

## Overview

The conversation starter cog pulls discussion questions from a
pre-loaded database (loaded from a Google Sheet via Python module) and
posts them in the channel. Questions are displayed bilingually (Spanish
+ English), with the order determined by the channel's configured
language.

Categories: General, Philosophical, Would You Rather, and Other.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$topic [category]` / `$top` | Post a random topic from a category. Defaults to `general`. Categories: `general` / `1`, `phil` / `2`, `would` / `3`, `other` / `4`. | None | 5s/user |
| `$lst` / `$list` | List all available topic categories with descriptions. | None | None |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `CONVO_SPA_CHANNELS` | Root `config.py` | (baked-in list) | Channels where Spanish is the primary language (English shown as subtitle). |

## Behavior

- **Spanish-primary channels** (`CONVO_SPA_CHANNELS`): Title in Spanish,
  English in description.
- **Other channels**: Title in English, Spanish in description.

## Implementation notes

- Questions are loaded at import time from
  `convo_starter_help.py`. The source is a Google Sheet (link available
  via `$lst`).
- The `get_random_question(table)` function picks a random question from
  the specified category.
- Embed color is randomized (from `base_cog.COLORS`).

> TODO: Document how to update the question database (Google Sheet →
> Python module export).
