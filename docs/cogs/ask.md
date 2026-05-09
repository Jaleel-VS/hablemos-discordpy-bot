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

## Implementation notes

- The cog uses `gemini-2.0-flash-lite` as the model (configurable in
  `self.model_name`).
- Gemini calls are sync, so they're wrapped in `loop.run_in_executor`
  with a 30-second timeout.
- Responses are split into pages at logical boundaries (code block ends,
  double newlines, or single newlines) to avoid mid-sentence breaks.
- The `PageView` provides ◀ and ▶ buttons to navigate pages (only
  visible to the command author).
- If the response is blocked by safety filters or rate-limited, a
  user-friendly error message is shown.

## Related

- [`./quote_generator.md`](./quote_generator.md) — another Gemini-powered
  feature.
- [`./summary.md`](./summary.md) — Gemini-based message summarization.
