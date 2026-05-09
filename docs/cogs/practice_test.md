# Practice Test (`practice_test_cog`)

Prototype Components V2-based practice flow.

## Overview

The practice test cog is a **prototype** for a future UI-driven practice
system using Discord's Components V2 (LayoutView, Container, etc.). It's
not production-ready — it uses hardcoded sample cards and has no
database persistence.

Purpose: test LayoutView interactions, button callbacks, and multi-step
flows before integrating with the full practice system.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$practice` | Start a sample practice session with 4 hardcoded cards. Interactive buttons for answer selection. | None |

## Gameplay

1. User runs `$practice`.
2. Bot shows a question with multiple-choice buttons (one correct, three
   distractors).
3. User clicks an answer.
4. Bot shows a result screen (correct/incorrect) with a "Next" button.
5. Repeat for all cards.
6. Final summary screen shows correct/total.

## Implementation notes

- The cog uses `QuestionView` (multiple-choice buttons) and `ResultView`
  (feedback + next button) as separate LayoutView subclasses.
- The `_make_callback` pattern creates per-button callbacks with closure
  over the choice.
- No database, no scoring persistence — purely a UI sandbox.

> TODO: Integrate with the real practice system (FSRS scheduling,
> `practice_cards` table, spaced repetition logic) once the UI patterns
> are validated. See [`./practice.md`](./practice.md) for the current
> production practice system.

## Related

- [`./practice.md`](./practice.md) — FSRS-based practice system (current
  production).
- [`./dictation.md`](./dictation.md) — another practice feature.
