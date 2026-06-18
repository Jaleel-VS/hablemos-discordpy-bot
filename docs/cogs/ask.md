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
| `GEMINI_ASK_MODEL` | `cogs/ask_cog/config.py` | `gemini-3.5-flash` | Gemini model id sent to `generateContent`. Override to bump models without a code change (see the [model list](https://ai.google.dev/gemini-api/docs/models)). |

## Implementation notes

- The cog uses the model named in `MODEL_NAME` (env-overridable via
  `GEMINI_ASK_MODEL`); the default is `gemini-3.5-flash`.
- Gemini calls are sync, so they're wrapped in `loop.run_in_executor`
  with a 30-second timeout.
- Responses are split into pages at logical boundaries (code block ends,
  double newlines, or single newlines) to avoid mid-sentence breaks.
- The `PageView` provides ◀ and ▶ buttons to navigate pages (only
  visible to the command author).
- Errors from the Gemini SDK are caught as
  `google.genai.errors.ClientError` / `ServerError` and mapped to
  user-friendly messages by HTTP status code (400, 401/403, 404, 429,
  5xx). A 404 specifically prompts the operator to set
  `GEMINI_ASK_MODEL` to a supported model.

## Related

- [`./quote_generator.md`](./quote_generator.md) — another Gemini-powered
  feature.
- [`./summary.md`](./summary.md) — Gemini-based message summarization.
