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

## Implementation notes

- The cog uses `GeminiClient` (in `gemini_client.py`) to call the Gemini
  API.
- Message parsing is in `message_parser.py` (`parse_message_link`
  function).
- Summaries are cached in `SummaryCache` (in `cache.py`) with a 1-hour
  TTL.
- The prompt template is in `gemini_client.py` (customizable for
  topic-focused summaries).

## Related

- [`./ask.md`](./ask.md) — another Gemini-powered feature.
- [`./conversation.md`](./conversation.md) — AI-generated conversations.
