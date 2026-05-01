# Dictation Feature Spec

## Overview

Audio dictation exercise: bot plays a sentence, user types what they heard. Pure listening + writing — no translation.

## Languages & Directions

- 🇪🇸 **Spanish dictation** — audio in Spanish, user types in Spanish (for Spanish learners)
- 🇬🇧 **English dictation** — audio in English, user types in English (for English learners)

## Tiers

### Beginner (A1-A2)
- Short sentences: 5-10 words
- Common vocabulary, present tense, basic structures
- Example ES: "Mi hermano trabaja en un hospital."
- Example EN: "The cat is sleeping on the couch."

### Intermediate+ (B1-B2)
- Longer sentences: 10-20 words
- Subjunctive, past tenses, idioms, connectors
- Example ES: "Aunque lloviera todo el día, no cancelaríamos el viaje."
- Example EN: "If I had known about the delay, I would have taken a different route."

## Sentence Generation

- AI-generated via subagents (Gemini)
- Pre-generated and stored in DB
- Tagged by language and level

## Audio (TTS)

- **Engine:** Google Cloud TTS — Gemini 2.5 Flash TTS
  - Style prompt: "Read aloud clearly and naturally, like a native speaker in a casual conversation."
  - ~$0.20 for all 200 sentences (negligible cost)
- **Spanish voices:** Achird (M), Charon (M), Kore (F), Leda (F), Sulafat (F)
- **English voices:** Achernar (F), Charon (M), Fenrir (M), Kore (F), Puck (M)
- **Pre-rendered:** audio generated at sentence creation time, stored as MP3
- **Storage:** S3 bucket `hablemos-dictation-195950944512` (us-east-1, private)
  - IAM user `hablemos-bot-s3-reader` with GetObject on `audio/*`
  - Bot fetches via `aioboto3`, sends as Discord attachment

## Scoring

- **Max score: 4 points**
- Start at 4, deduct for errors:
  - Wrong/missing/extra word → higher deduction
  - Accent error (e.g., "el" vs "él", "mas" vs "más") → smaller deduction
  - Minor typo (1-2 char Levenshtein distance) → smaller deduction
- Fuzzy matching to distinguish typos from actual errors
- Punctuation ignored in scoring

## Discord UX

- Slash command: `/dictation`
  - Options: `language` (Spanish/English), `level` (Beginner/Intermediate+)
- Bot sends audio file as Discord attachment
- User types their answer as a message
- Bot replies with:
  - Score (X/4)
  - The correct sentence
  - Highlighted corrections (what they got wrong)
- One example sentence per language shown in help/description

## Not Yet Included

- Translation mode (listen in L2, type in L1)
- Leaderboard/XP integration
- Repeat/replay button
- Streak tracking
- Difficulty auto-adjustment
