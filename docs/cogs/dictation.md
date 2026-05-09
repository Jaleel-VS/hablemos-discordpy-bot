# Dictation (`dictation_cog`)

Audio listening exercises for language practice.

## Overview

The dictation cog provides audio-based listening comprehension
exercises. Users select a language and level, listen to an audio clip
(fetched from S3), and type what they hear. The bot scores answers based
on edit distance (Levenshtein) and records high scores.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/dictation <language> <level>` | Start a dictation exercise. Languages: Spanish (🇪🇸), English (🇬🇧). Levels: Beginner (🟢), Intermediate+ (🟡). | None |

## Configuration

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Env vars | unset | **Required** for S3 audio fetching. |
| `S3_BUCKET` | `cogs/dictation_cog/config.py` | (baked-in) | S3 bucket name for audio files. |
| `S3_REGION` | `cogs/dictation_cog/config.py` | (baked-in) | S3 region. |
| `ANSWER_TIMEOUT_SECONDS` | `cogs/dictation_cog/config.py` | 60 | How long users have to answer. |
| `MAX_SCORE` | `cogs/dictation_cog/config.py` | 4 | Perfect score (emoji: 🎉). |

## Scoring

Answers are scored 0–4 based on normalized Levenshtein distance:

- **4 (🎉)**: Perfect or near-perfect.
- **3 (😊)**: Minor typos.
- **2 (🙂)**: Significant errors but mostly correct.
- **1 (😕)**: Many errors.
- **0 (😢)**: Very wrong or empty.

High scores are tracked in the `dictation_scores` table (one row per
user per sentence, retains best attempt).

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `dictation_sentences` | `DictationMixin` | Audio clips with text, language, level, S3 URL. |
| `dictation_scores` | `DictationMixin` | User high scores per sentence. |

See [`../database.md`](../database.md) for query methods (in
`DictationMixin`).

## Implementation notes

- The cog uses `aioboto3` to fetch audio from S3 on demand (not cached
  locally).
- One pending dictation per channel (enforced via `self._pending` dict).
- The `on_message` listener checks every message in channels with
  pending dictations and scores answers.
- Timeout is handled via `asyncio` task that clears the pending state
  after `ANSWER_TIMEOUT_SECONDS`.

## Related

- [`./practice.md`](./practice.md) — FSRS-based practice system.
- [`./crossword.md`](./crossword.md) — another practice feature with
  scoring.
