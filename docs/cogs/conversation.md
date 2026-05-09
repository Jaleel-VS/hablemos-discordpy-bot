# Conversation (`conversation_cog`)

AI-generated bilingual conversations for language practice.

## Overview

The conversation cog uses Google Gemini to generate realistic
Spanish-English conversations based on user-selected categories,
proficiency levels, and length. Useful for reading comprehension and
vocabulary building.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$conversation <category> [level] [language] [length]` / `$convo` | Generate a conversation. Categories: `general`, `travel`, `food`, etc. Levels: `beginner`, `intermediate`, `advanced`. Languages: `en`/`es` (display language, not practice language). Length: number of exchanges (default 5, max 15). | None | 30s/user |

## Configuration

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `GEMINI_API_KEY` | Root `config.py` | unset | **Required** for this cog to load. |

## Implementation notes

- The cog uses `ConversationGeminiClient` (in `gemini_client.py`) to
  call the Gemini API.
- Categories and levels are defined in `conversation_data.py`
  (`CATEGORIES`, `LEVELS`, `LANGUAGES`).
- Aliases are supported for all parameters (e.g., `1` for `beginner`,
  `g` for `general`, `spa` for `es`).
- Conversations are generated on-demand (not cached).
- Background tasks are tracked in `self._background_tasks` to allow
  cleanup on cog unload.

## Related

- [`./ask.md`](./ask.md) — another Gemini-powered feature.
- [`./summary.md`](./summary.md) — Gemini-based message summarization.
