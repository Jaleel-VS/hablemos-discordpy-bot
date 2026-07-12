# Plan: Conjugation game (Activity)

> **Status: MVP SHIPPED.** The conjugation sprint is built and documented in
> [`../activity.md`](../activity.md) (games framework), the launcher in
> [`../cogs/wordle.md`](../cogs/wordle.md), and the commands in
> [`../commands.md`](../commands.md). This file is kept as the design rationale
> and the **growth path** (below) for later tenses/modes. The "MVP" checklist is
> retained for history with items checked off.
>
> One deviation from the original plan: the precomputed paradigm JSON is a
> **committed artifact** loaded at runtime (exactly like the Wordle word lists),
> so **no Dockerfile change was needed** — the existing `COPY backend/ ./` ships
> it and verbecc never touches the runtime image. Simpler than the build-stage
> step the plan first assumed.

A Spanish **verb-conjugation** game for the embedded [Discord Activity](../activity.md),
modeled on [Conjuguemos](https://conjuguemos.com/). It is the **second game** in
the Activity, sitting beside Wordle in the same game registry.

## Why this fits the existing architecture

The Activity was built as a **registry over a game-engine contract** precisely so
a second game touches only its own module. Conjugation is `game_key:
"conjugation"` and reuses, unchanged:

- **Generic routes** — `POST /api/games/{key}/start`, `/guess`, `/stats`,
  `GET /api/games` (`app/games/routes.py`).
- **Sealed server-side state** — Fernet-sealed token round-trips through the
  client so the answer never leaks and can't be forged (`app/games/sealed_state.py`).
- **Game-agnostic persistence** — `game_results` and `game_stats` keyed by
  `game_key` (see [`../database.md`](../database.md)).
- **Results posting** — the bot's `activity_results_cog` already posts finished
  **daily** rows; it is game-agnostic and needs no change.
- **The menu/hub** — the Activity home screen lists whatever `GET /api/games`
  returns. Registering a second game is what makes the menu appear (with one
  game it boots straight into that game).

New surface area is small: one `app/games/conjugation/` module + one registry
line, a frontend game component, and a `$conjuga` launcher cog mirroring
`wordle_cog`.

### Relationship to the existing `/conjugate` cog

There is already a native-Discord `conjugation_cog` (`/conjugate`, embed-based).
It stays as-is for now. The Activity version is the richer, timed, motion-driven
experience. Retiring `/conjugate` is a **later, separate** decision — not part of
this MVP.

## The game (MVP)

**Conjugación — a 60-second sprint.** The proven Conjuguemos loop:

1. **Prompt:** a verb (with English gloss) + a subject pronoun + a tense.
   e.g. **hablar** *(to speak)* → **nosotros** · *pretérito*.
2. **Answer:** type the conjugated form, Enter to submit.
3. **Feedback:** instant green/red. Wrong → briefly show the correct form and
   **requeue** that verb later in the round (the Conjuguemos "repeat your
   mistakes" mechanic — the actual learning driver).
4. **Score:** number correct within the time window + longest streak.
5. **End screen:** score, longest streak, and the list of verbs missed.

### Accent handling

Reuse the **ñ-safe normalize** built for Wordle. Policy: an answer that is
correct except for missing/extra accents is accepted **but flagged** —
`¡Casi! → hablé` — and still counts, so beginners aren't hard-blocked but see the
correct accents. Wrong stem/ending is simply wrong. (Confirm this exact policy
with the user before building; it's the one UX judgment call.)

### Configuration (start screen)

- **Verb set:** high-frequency / regular -ar / -er / -ir / irregulars.
- **Tense(s):** presente, pretérito, imperfecto, futuro to start; subjuntivo /
  imperativo as a fast-follow (verbecc supplies them for free).
- **Pronouns:** all, or "all but vosotros" (Conjuguemos offers this).

### Daily vs freeplay

Mirror Wordle exactly:

- **Daily** — a deterministic verb/tense list seeded by date; counts toward
  streaks and **posts to the results channel** via the existing cog.
- **Freeplay** — random, no streaks, never posts.

## Verb data: verbecc (LOCKED IN)

Conjugation paradigms come from **[`verbecc`](https://pypi.org/project/verbecc/)**,
not hand-maintained JSON.

- **verbecc 2.0.2**, Python ≥3.9 (our backend is 3.12). Full Spanish paradigms
  via `Moods.es.*` (Indicativo, Subjuntivo, Imperativo, …) and `Tenses.es.*`
  (Presente, Pretérito, …), including irregulars and ML-predicted unknowns.
- **License: LGPLv3.** We import it as an unmodified library dependency; we do
  not modify or statically link/redistribute it, so LGPL obligations are met.
- **API shape:**

  ```python
  from verbecc import Conjugator
  cg = Conjugator(lang="es")
  cg.conjugate("hablar")["moods"]["indicativo"]["presente"]
  # -> ["yo hablo", "tú hablas", "él habla", ...]
  ```

  (Confirm the exact 2.0.2 accessor against the installed package in `.venv/`
  before coding — the README shows both a `Conjugator`/dict form and a newer
  `CompleteConjugator` + `Moods`/`Tenses` enum form.)

### The one real cost: dependency weight

verbecc pulls in **scikit-learn + scipy + numpy** (the ML layer for predicting
unfamiliar verbs). That is a heavy add to the Activity's Docker image and slow to
import at request time.

**Recommended mitigation — precompute at build time.** Run verbecc **once during
the Docker build** (or a `scripts/` generator) over our curated verb list and
emit a compact `conjugation_paradigms.json` (verb → mood → tense → forms). The
**runtime** image then reads that JSON and needs none of scikit-learn/scipy/numpy
on the hot path. This keeps verbecc as the authoritative source of truth while
keeping the deployed image lean and fast.

- **Seed verb list:** start from `cogs/conjugation_cog/verb_data.json` (59 verbs,
  hand-curated) for the *word list*, but generate the *forms* with verbecc so we
  get all tenses/moods correctly instead of the current 3 hand-typed tenses.
- Fallback if precompute is deemed overkill for MVP: depend on verbecc directly
  and conjugate on `/start` (cache in-process). Simpler, heavier image. Prefer
  the precompute path.

## UX / UI north star

Same craft bar as the Wordle rework (the `impeccable` skill guidance): OKLCH
palette, no pure black/white, fit-to-viewport (no scrolling), self-hosted fonts,
ease-out (quart/quint) motion, no bounce.

The **motion signature** for this game is the **prompt swap** — the answered
prompt slides/fades out as the next one enters — plus a satisfying **streak
counter**. That's the conjugation analog to Wordle's tile flip.

## Task breakdown (MVP — shipped)

- [x] `scripts/generate_conjugation_paradigms.py` — verbecc over the seed verb
      list → `activity/backend/app/games/data/conjugation_paradigms.json`
      (59 verbs × 4 tenses; `pasar` via a manual fallback for a verbecc bug).
- [x] Committed the JSON as a runtime artifact (no Docker/build change; verbecc
      excluded from the runtime image).
- [x] `app/games/conjugation/` — `normalize.py` (3-way accent-aware grading),
      `data.py` (loader + untrusted-`options` config resolution + question
      picker), `engine.py` (60s server-authoritative timer, streaks,
      answer-free view). Registered in `registry.py`.
- [x] Extended the `GameEngine.new_game` contract with an optional `options`
      passthrough (Wordle ignores it) and threaded it through `routes.py`.
- [x] Frontend `src/games/conjugation/` — `Setup` (verb set / tenses /
      pronouns + daily quick-start), `Sprint` (prompt-swap motion, live timer,
      streak pills, inline feedback), `Summary` (score + best streak + review
      misses). Plus the `Home` hub and `src/games/registry.tsx`.
- [x] Shared launcher `cogs/utils/activity_launch.py`; `$conjuga` cog + `$wordle`
      refactored onto it.
- [x] Tests: `activity/backend/tests/test_conjugation.py` (grading, config,
      sprint flow) + conjugation route tests. Full suite green.
- [x] Docs folded into `activity.md`, `commands.md`, `cogs/wordle.md`, `README.md`.

**Accent policy shipped:** accept-but-flag (`close` counts, UI shows the accent).
**Tense set shipped:** presente, pretérito, imperfecto, futuro.
**Modes shipped:** Reto diario (deterministic 60s, streaks, posts), Sprint 60s
(freeplay timed), and Práctica libre (freeplay **untimed** — no clock, ends on
"Terminar"). The untimed mode rides a `timed` flag in `options` and an explicit
`finish` action added to the `GameEngine.submit` contract.

## Growth path (post-MVP)

- More tenses/moods: imperfecto, subjuntivo, imperativo, compound tenses
  (verbecc already provides them).
- A dedicated Conjuguemos-style "review your misses" round after the sprint.
- Per-tense / per-pronoun accuracy stats in the stats screen.
- Eventually a lightweight leaderboard or head-to-head mode (Conjuguemos Live
  analog) — larger effort, out of MVP scope.
