# Conjugation (`conjugation_cog`)

Interactive Spanish verb conjugation practice using Components V2.

## Overview

The conjugation cog provides a practice session where users conjugate
Spanish verbs across different tenses and pronouns. Sessions are
ephemeral, button-driven, and track accuracy. Verb data is stored in
`conjugation_verbs` and `conjugation_forms` tables.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/conjugate [mode] [tense]` | Start a conjugation practice session. Modes: `learn` (shows errors inline), `test` (shows all answers at end). Tenses: `presente`, `pretérito`, `imperfecto`, `futuro`, `condicional`, etc. (11 total). | None |

## Implementation notes

- The cog uses `ConjugationSession` (in `session.py`) to track progress.
- `build_question_view`, `build_result_view`, and `build_summary_view`
  (in `views.py`) provide the UI.
- Answers are normalized (lowercase, stripped) for comparison.
- Tenses:
  - Simple: presente, pretérito, imperfecto, futuro, condicional.
  - Compound: pretérito perfecto, pluscuamperfecto.
  - Subjunctive: subjuntivo presente, subjuntivo imperfecto.
  - Imperative: imperativo afirmativo, imperativo negativo.

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `conjugation_verbs` | N/A | Spanish verbs (infinitive, translation). |
| `conjugation_forms` | N/A | Conjugated forms (verb ID, tense, pronoun, form). |

> TODO: Add a mixin to `db/` for conjugation queries if not already
> present.

## Related

- [`./practice.md`](./practice.md) — FSRS-based vocab practice.
- [`./dictation.md`](./dictation.md) — another practice feature.
