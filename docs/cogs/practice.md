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

## Implementation notes

- Cards are stored in `practice_cards` (see
  [`../database.md`](../database.md)).
- The cog uses `PracticeSession` (in `session.py`) to track progress.
- `build_question_view`, `build_result_view`, and `build_summary_view`
  (in `views.py`) provide the UI.
- FSRS scheduling logic is in `srs.py` (`review_card` function).
- New cards are generated on-demand via Gemini (see
  `gemini.py`/`PracticeGeminiClient`).
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
