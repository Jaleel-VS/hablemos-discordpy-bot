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
| `GEMINI_CONVERSATION_MODEL` | resolved by `cogs/utils/gemini/` | falls back to `GEMINI_DEFAULT_MODEL`, then `gemini-3.5-flash` | Per-feature model override for `$convo` generation. |

## Implementation notes

- The cog goes through ``self.bot.gemini.run(CONVERSATION_PROMPT, inp)`` —
  it doesn't construct ``genai.Client`` itself. Model resolution, rate
  limiting, retry-on-5xx, and HTTP-code-aware error mapping all live
  inside ``cogs/utils/gemini/`` (see
  [`../architecture.md`](../architecture.md#gemini-deep-module)).
- ``CONVERSATION_PROMPT`` lives in ``prompts.py`` and owns the full
  pipeline: render the long structured-output template, vary
  generation temperature per level via ``resolve_temperature`` (0.7 /
  0.8 / 0.9 for beginner / intermediate / advanced), and parse the
  ``SCENARIO:`` / ``SPEAKER1:`` / ``SPEAKER2:`` / ``CONVERSATION:``
  response into a typed :class:`ParsedConversation` dataclass
  (returns ``None`` if any required field is missing).
- Categories and levels are defined in ``conversation_data.py``
  (``CATEGORIES``, ``LEVELS``, ``LANGUAGES``).
- Aliases are supported for all parameters (e.g., `1` for `beginner`,
  `g` for `general`, `spa` for `es`).
- Conversations are generated on-demand (not cached).
- Background tasks are tracked in ``self._background_tasks`` to allow
  cleanup on cog unload.
- Per-iteration ``GeminiError`` handling in ``generate_conversations_batch``
  keeps batch semantics: a transient failure on one scenario logs a
  warning and the iteration is counted as a failure; the loop
  continues with the next scenario.

## Related

- [`./ask.md`](./ask.md) — another Gemini-powered feature.
- [`./summary.md`](./summary.md) — Gemini-based message summarization.
