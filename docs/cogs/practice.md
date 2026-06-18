# Practice (`practice_cog`)

Vocabulary practice with spaced repetition (SRS) using FSRS.

## Overview

The practice cog provides a Clozemaster-style cloze sentence practice
system. Users see a sentence with a blank, type the missing word, and
the bot schedules future reviews using the FSRS (Free Spaced Repetition
Scheduler) algorithm. Cards move through SRS states (new, learning,
review, relearning) based on performance.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/practice [mode] [due_only]` | Start a practice session. Modes: `learn` (shows errors inline), `test` (shows all answers at end). `due_only`: if true, only reviews cards due now. | None |
| `/practice_stats` | Show your practice stats: total cards, new/learning/review counts, cards due. | None |

## Configuration

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `GEMINI_API_KEY` | Root `config.py` | unset | **Required** for generating new cards on-demand. |
| `GEMINI_PRACTICE_MODEL` | resolved by `cogs/utils/gemini/` | falls back to `GEMINI_DEFAULT_MODEL`, then `gemini-3.5-flash` | Per-feature model override for sentence generation. |

## Implementation notes

- Cards are stored in `practice_cards` (see
  [`../database.md`](../database.md)).
- The cog uses `PracticeSession` (in `session.py`) to track progress.
- `build_question_view`, `build_result_view`, and `build_summary_view`
  (in `views.py`) provide the UI.
- FSRS scheduling logic is in `srs.py` (`review_card` function).
- New cards are seeded via
  ``await self.bot.gemini.run(PRACTICE_SENTENCE_PROMPT, PracticeWord(...))``
  (see [`../architecture.md`](../architecture.md#gemini-deep-module)).
  ``PRACTICE_SENTENCE_PROMPT`` lives in ``prompts.py`` and owns the
  full pipeline: format the sentence template, validate that Gemini's
  response contains the target word (word-boundary regex,
  case-insensitive), and build the cloze blank by substituting
  ``___`` for the matched span. If the response doesn't contain the
  word, ``parse`` returns ``None`` and the card is skipped.
- ``GeminiError`` raised by the runtime (404, 429, 5xx after retry)
  is caught per word in ``$practice seed`` so a transient failure
  on one word doesn't abort the batch — it logs a warning and the
  word is counted as failed in the progress UI.
- Seed words are in `seed_words.py` (`SEED_WORDS` list).

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `practice_cards` | `PracticeMixin` | Cloze cards with SRS state. Columns: `user_id`, `word`, `sentence_with_blank`, `sentence_translation`, `translation`, `level`, `due_date`, `interval`, `ease_factor`, `state`, `created_at`, `reviewed_at`. |

See [`../database.md`](../database.md) for query methods (in
`PracticeMixin`).

## Related

- [`./conjugation.md`](./conjugation.md) — verb conjugation practice.
- [`./dictation.md`](./dictation.md) — audio listening practice.
- [`./practice_test.md`](./practice_test.md) — prototype UI (not SRS).
