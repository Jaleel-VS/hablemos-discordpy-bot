# Ask (`ask_cog`)

Owner-only Gemini Q&A with paginated responses.

## Overview

The ask cog provides a single command (`$ask`) that sends a question to
Google's Gemini AI and displays the response. Responses are
automatically paginated if they exceed embed character limits. The owner
can choose to post the response publicly or ephemerally via a visibility
toggle.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$ask <question>` | Ask Gemini anything. Shows a visibility picker (public/ephemeral) after generating the response. | Owner-only |

## Configuration

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `GEMINI_API_KEY` | Root `config.py` | unset | **Required** for this cog to load. |
| `GEMINI_ASK_MODEL` | resolved by `cogs/utils/gemini/` | falls back to `GEMINI_DEFAULT_MODEL`, then `gemini-3.5-flash` | Gemini model id used for `$ask`. Override to bump models without a code change. Same pattern as every other Gemini-using feature — see [`../architecture.md`](../architecture.md#gemini-deep-module). |

## Implementation notes

- The cog goes through ``self.bot.gemini.run(ASK_PROMPT, question)`` — it
  doesn't construct ``genai.Client`` itself. Model resolution, rate
  limiting, retry-on-5xx, and HTTP-code-aware error mapping all live
  inside ``cogs/utils/gemini/`` (see
  [`../architecture.md`](../architecture.md#gemini-deep-module)).
- ``ASK_PROMPT`` is declared in ``cogs/ask_cog/prompts.py`` as a
  stateless singleton ``Prompt[str, str]``. ``feature = "ask"`` is
  what makes ``GEMINI_ASK_MODEL`` the per-feature env override.
- Failures raise ``GeminiError`` with a ``.user_message`` already
  formatted for the user; the cog catches it in one ``except`` clause
  and edits the processing message with that string. A 404 (model
  unavailable) tells the operator to set ``GEMINI_ASK_MODEL``.
- ``$ask`` adds a 30-second wall-clock timeout on top via
  ``asyncio.wait_for`` for snappy failure when Gemini hangs.
- Responses are split into pages at logical boundaries (code block
  ends, double newlines, or single newlines) to avoid mid-sentence
  breaks.
- The ``PageView`` provides ◀ and ▶ buttons to navigate pages (only
  visible to the command author).

## Related

- [`./quote_generator.md`](./quote_generator.md) — another Gemini-powered
  feature.
- [`./summary.md`](./summary.md) — Gemini-based message summarization.
