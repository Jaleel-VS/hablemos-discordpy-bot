# Summary (`summary_cog`)

AI-powered conversation summaries using Google Gemini.

## Overview

The summary cog generates high-level summaries of Discord conversations
by fetching messages between two links and passing them to Gemini. It
caches results to avoid re-processing the same range.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$summarize <start_link> <end_link> [topic]` / `$summary` / `$sum` | Summarize a conversation between two message links. Optional `[topic]` focuses the summary. Max 500 messages. | `manage_messages` | 30s/user |

## Configuration

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `GEMINI_API_KEY` | Root `config.py` | unset | **Required** for this cog to load. |
| `GEMINI_SUMMARY_MODEL` | resolved by `cogs/utils/gemini/` | falls back to `GEMINI_DEFAULT_MODEL`, then `gemini-3.5-flash` | Per-feature model override for `$sum` and `$sumtopics`. |

## Implementation notes

- The cog goes through ``self.bot.gemini.run(...)`` — it doesn't
  construct ``genai.Client`` itself. Model resolution, rate limiting,
  retry-on-5xx, and HTTP-code-aware error mapping all live inside
  ``cogs/utils/gemini/`` (see
  [`../architecture.md`](../architecture.md#gemini-deep-module)).
- Prompts live in ``cogs/summary_cog/prompts.py`` as stateless
  ``Prompt[I, O]`` singletons:
  - ``SUMMARY_PROMPT`` — overview summary (no topic).
  - ``FOCUSED_SUMMARY_PROMPT`` — topic-focused, includes per-message
    evidence links.
  - ``SUGGEST_TOPICS_PROMPT`` — proposes topics worth investigating.
  All three share ``feature = "summary"`` so a single
  ``GEMINI_SUMMARY_MODEL`` env var bumps the model for every variant.
- Failures raise ``GeminiError``; the cog catches it in one ``except``
  clause and edits the processing message with ``e.user_message``
  (already formatted: 404 names the env var, 429 says "try again in a
  minute", etc.).
- Message parsing is in ``message_parser.py`` (``parse_message_link``).
- Summaries are cached in ``SummaryCache`` (``cache.py``) with a 1-hour
  TTL. The cache key includes the topic suffix so overview and
  focused summaries don't collide.
## Related

- [`./ask.md`](./ask.md) — another Gemini-powered feature.
- [`./conversation.md`](./conversation.md) — AI-generated conversations.
