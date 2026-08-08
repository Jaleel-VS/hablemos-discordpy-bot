# Discord Activity (embedded games)

The bot has a companion **Discord Activity** — an embedded web app that runs
inside Discord's client (the same mechanism as YouTube Watch Together or the
official word games). It hosts Spanish-language games — a Spanish Wordle, a
timed verb-conjugation sprint, and a Clozemaster-style fill-in-the-blank game —
behind a game **hub/menu**. When a daily game finishes, the result posts to a
configured channel.

The Activity is a **separate Railway web service** from the gateway bot. They
share the same PostgreSQL database. The code lives in
[`../activity/`](../activity/) (see its
[`README.md`](../activity/README.md) for the internal layout).

> **Status:** Phases 0–2 built. Phase 0 (OAuth handshake) is live in
> production. Phase 1 is the extensible game framework — **Spanish Wordle**, a
> **Conjugation** sprint, and a **Cloze** (fill-in-the-blank) game (all daily +
> freeplay, stats/streaks in the shared Postgres), reached through a game hub.
> Phase 2 is the bot posting finished **daily** results to a configured channel.

## How it works

```
Discord client (iframe)  ──postMessage RPC──►  Vite/React SPA (activity/frontend)
        │                                             │  fetch("/.proxy/api/…")
        │ served via <CLIENT_ID>.discordsays.com      ▼
        │                                       FastAPI (activity/backend)
        │                                       - POST /api/token  (OAuth exchange)
        │                                       - POST /api/me      (verified identity)
        ▼                                       - game logic + results ─► Postgres
Discord API (oauth2/token, users/@me)                                        │
                                                                             ▼
                                          gateway bot polls results, posts card to channel
```

The Activity **cannot post channel messages itself** — that's the bot's job.
Identity is always verified server-side via `users/@me`; the iframe is
tamperable, so a client-sent user id is never trusted.

### Results posting (Phase 2)

When a player finishes a **daily** game, the Activity writes a `game_results`
row (`posted_at` NULL). The bot's `activity_results_cog` runs a `tasks.loop`
that polls for unposted daily rows, posts an emoji-grid card to
`ACTIVITY_RESULTS_CHANNEL_ID` mentioning the player, then sets `posted_at`.
This keeps the bot gateway-only (no inbound HTTP) and reuses its DB pool.
Freeplay results are never posted. The bot **reads** `game_results` but never
creates the table — the Activity owns that schema — so the poller tolerates the
table not existing yet. See [`cogs/activity_results.md`](./cogs/activity_results.md).

### The `/.proxy/` rule (the #1 gotcha)

Inside Discord, everything the iframe fetches is routed through
`https://<CLIENT_ID>.discordsays.com` under a strict CSP. **Every** backend
call from the SPA must use the `/.proxy/` prefix (e.g.
`fetch("/.proxy/api/token")`) **and** be covered by a URL Mapping, or it
silently fails with `blocked:csp`. Discord's proxy strips `/.proxy` before the
request reaches FastAPI, so the FastAPI routes are declared without it
(`/api/token`).

### Launching

The bot launches the Activity from a command button (`$wordle`, `$conjuga`) via
the `LAUNCH_ACTIVITY` interaction callback — see
[`cogs/wordle.md`](./cogs/wordle.md). Discord opens it in the channel the button
was clicked from (servers and DMs both work — **no voice channel required**).

Activities also appear in the 🚀 Activity Shelf. While the app is unpublished it
only appears there for the **owner account** (or team members) with **Developer
Mode** on and the tested **platform** checked under Activities → Supported
Platforms. A first launch shows a "not made by Discord" confirmation — expected
for a private test app.

## Games framework (Phase 1)

The backend is a small **registry over a game-engine contract**, so adding a
game touches only its own module:

- `app/games/base.py` — the `GameEngine` protocol
  (`new_game` / `submit` / `is_over` / `result_payload`) and shared types.
- `app/games/registry.py` — the one place that lists games. Add a game = add
  one line here.
- `app/games/routes.py` — generic routes for **every** game:
  `POST /api/games/{key}/start`, `/guess`, `/stats`, and `GET /api/games`.
  `start` accepts an optional untrusted `options` object for game-specific
  config (the conjugation game's verb set / tenses / pronouns); each engine
  normalizes or ignores it.
- `app/games/wordle/` — the Wordle game (see below).
- `app/games/conjugation/` — the conjugation sprint (see below).
- `app/games/cloze/` — the fill-in-the-blank game (see below).

The frontend mirrors this: `GET /api/games` drives a **hub/menu** listing every
game. With a single game registered the app boots straight into it (no menu
friction); with two or more it shows the hub. A frontend registry
(`src/games/registry.tsx`) maps each game key to its React component and card
styling.

Game state is **stateless on the server**: it round-trips through the client
between guesses, but **sealed** (`sealed_state.py` — Fernet encrypt+authenticate
keyed off `DISCORD_CLIENT_SECRET`) so the client holds an opaque token it can't
read (the answer lives in the state) or forge. Every guess unseals,
re-validates via the engine, and re-seals. The client only ever sees the
opaque token and an answer-free `view`.

### Spanish Wordle (`app/games/wordle/`)

- **27-letter alphabet, Ñ distinct, accents stripped** (`normalize.py` — with
  the NFD ñ-protection). Word lists in `app/games/data/`
  (`wordle_answers.txt` curated, `wordle_guesses.txt` permissive superset).
- **Two-pass duplicate-safe scorer** (`scorer.py`) — greens claim letters
  first, then yellows from what remains.
- **Daily** (deterministic by date, counts toward streaks, will post to a
  channel) and **freeplay** (random, no streaks, no posting).
- The answer is authoritative on the server and never sent to the client until
  the game ends.
- **Daily expires at date rollover.** A daily `submit` is rejected once the
  state's `date` is no longer today, so a saved token can't be finished days
  later (which `compute_streak`, keyed on consecutive `puzzle_no`, would
  otherwise still credit). Freeplay has no date gate.

### Conjugation sprint (`app/games/conjugation/`)

A timed verb-conjugation drill modeled on Conjuguemos: show a verb + subject
pronoun + tense, the player types the conjugated form, get instant graded
feedback, repeat against a **60-second** clock. Score = correct answers before
time runs out.

- **Data is precomputed, not live.** `scripts/generate_conjugation_paradigms.py`
  runs [verbecc](https://pypi.org/project/verbecc/) **offline** over a seed verb
  list (from `activity/backend/app/games/data/conjugation_seed.json`) and emits
  `app/games/data/conjugation_paradigms.json` (verb → tense → pronoun → form).
  verbecc trains an ML model on first import (~12s) and needs
  scikit-learn/scipy/numpy, so it is a **dev/build-time** dependency only — the
  runtime image just reads the committed JSON (like the Wordle word lists). Add
  a tense in the generator's `TENSES` map and regenerate to grow the game. The
  generator **refuses to write** (exit 1) if a verbecc change would drop any
  seed verb or tense — a silent shrink would shift the deterministic daily
  sequence and reduce freeplay pools; pass `--allow-drops` to accept reviewed
  drops. `tests/test_conjugation_data.py` guards the committed JSON the same way
  in CI (full seed grid present, no leaked pronoun prefixes).
- **Three-way grading** (`normalize.py`): `exact`, `close` (correct except
  accents — counts, but the UI flags it), `wrong`. Reuses the same ñ-safe
  accent handling as Wordle (ñ is a letter, not an accent).
- **Three modes.** **Reto diario** — a deterministic 60s sprint (hash of puzzle
  number + index) so everyone drills the same prompts; counts toward streaks and
  posts to the results channel. **Sprint 60s** — freeplay against the clock with
  the player's chosen verb set / tenses / pronouns. **Práctica libre** — the same
  freeplay pools but **untimed**: no deadline, ends only when the player taps
  "Terminar" (or leaves).
- **Timing is server-authoritative** for timed modes: every `submit` re-checks
  the deadline (a 1.5s grace covers request latency), so the client countdown is
  presentational only and can't be gamed. Untimed practice carries a `null`
  deadline and ends via an explicit `finish` action on `submit` (part of the
  shared `GameEngine` contract; games without an open-ended mode ignore it).
- Freeplay config and the `timed` flag ride in the `start` `options` object;
  the engine normalizes untrusted values, defaulting to the timed sprint.
- The pending answer lives in sealed state and is never in the client view
  until it's been submitted.
- **Daily anti-harvest.** The daily is a fixed, deterministic sequence shared by
  everyone, so revealing each form mid-run would let a player mash junk, read the
  answers, and restart to ace it. Two guards close this: (1) conjugation's
  per-answer feedback **withholds `expected` in daily mode** (the client gets the
  exact/close/wrong flag but not the correct form — disclosed only in the
  end-of-game recap; freeplay/practice reveals normally since there's nothing to
  game); (2) the shared `start` route **refuses a second daily** for a puzzle a
  player already finished (`409`) — applies to any game with a `puzzle_no`,
  Wordle included.
- **Known limit — the daily is honor-system, by design.** Because the backend
  is stateless (state round-trips as a sealed token) and the repo is
  open-source with a deterministic daily, a determined player *can* still cheat
  a daily score: the date→answer mapping is derivable from public code
  (`daily.py`), and a sealed token can be replayed/branched to brute-force
  Wordle guesses (each `submit` forks the same starting state). Truly closing
  this needs **server-side attempt consumption** — a per-`(user, game, puzzle)`
  progress row storing a monotonic guess high-water mark, rejecting stale/reused
  tokens — which re-introduces a per-guess DB round-trip we deliberately removed
  (verify-once + `_uid`). Since the only stake is a cosmetic emoji-grid post in a
  friendly server, we accept the honor-system boundary rather than pay that cost.
  Revisit if the daily leaderboard ever becomes competitive.

### Cloze (`app/games/cloze/`)

A Clozemaster-style **fill-in-the-blank** game. A short sentence is shown with
one content word blanked in the learner's **target language**, plus the full
sentence in the other language as context; the player supplies the missing word.
A round is a fixed **10 cards** — there is no clock (untimed, unlike the
conjugation sprint).

- **Two decks by target language.** `target="es"` blanks the Spanish word
  (English shown as context) for Spanish learners; `target="en"` is the mirror
  for English learners. The player picks their target on the setup screen; the
  daily defaults to the Spanish deck.
- **Two answer modes**, chosen at start (`answer_mode`): **`choice`** — 4-option
  multiple choice (the answer + 3 precomputed same-part-of-speech distractors);
  **`type`** — free text, graded with the **same ñ-safe 3-way
  `exact`/`close`/`wrong` grader reused from the conjugation game** (accents are
  flagged, not failed). MC options are shuffled deterministically per run.
- **Three difficulty bands** (`beginner`/`intermediate`/`advanced`) plus a mixed
  default, keyed off the source word's frequency + sentence complexity.
- **Content is precomputed, not live.**
  `scripts/generate_cloze_sentences.py` runs **offline** against Amazon Bedrock
  (Claude Haiku 4.5, via the author's `bedrock-how` AWS profile — the same path
  as the shell `how`/`howdo` helpers), batching sentence pairs and emitting
  `app/games/data/cloze_sentences.json` (~500 cards, evenly split across both
  decks and three difficulties). The generator validates every card in Python
  (exactly one blank, the answer present as a whole word or a pre-blanked
  sentence, exactly 3 distinct distractors, no answer/distractor collision —
  the distractor check strips accents to match the runtime grader's CLOSE
  tier), dedupes, and buckets by difficulty. It refuses to write when any
  (target, difficulty) bucket falls below `--min-fill` of target (default 80%,
  hard floor of one round) so a partial run can't ship a lopsided corpus. The
  **runtime never calls an LLM** — it just reads the committed JSON, the same
  rule the conjugation game follows with its verbecc paradigms. Re-run with
  `--merge` to grow the pool over time.
- **Content is machine-reviewed by a second, stronger model.** Structural
  checks can't catch a wrong translation, a grammatically-wrong answer, or a
  distractor that's actually a synonym. `scripts/review_cloze_sentences.py`
  grades every committed card with **Claude Opus 4.8** (a different, stronger
  model than the Haiku generator — not the same model checking its own
  homework), judging translation, answer correctness (incl. subjunctive/tense),
  distractor validity (real, correctly-spelled, right morphological form, not a
  synonym), and difficulty. The pipeline **fails closed**: a card the model
  can't grade after retries is quarantined, not shipped, and the corpus meta
  records a `survivors_all_passed` invariant so a commit can prove every shipped
  card was verified. Suspects are **quarantined** out of `cloze_sentences.json`
  into a sibling `cloze_sentences.quarantine.json` (never loaded at runtime) for
  human fix-and-reinstate; a `--decisions` file lets a human force-keep or
  force-quarantine specific ids. Run `--dry-run` first for a report without
  modifying the corpus. Both scripts share Bedrock plumbing in
  `scripts/_bedrock.py`. Two review passes over the initial 497 cards left
  **367 verified** (130 quarantined).
- **Daily** is a deterministic 10-card pick by date (hash of puzzle number +
  position, non-repeating within a round) so everyone drills the same cards; it
  counts toward streaks and posts to the results channel. Because it feeds
  streaks, the daily must be **completed** (all 10 cards answered) to count — an
  early "Terminar" is rejected and an abandoned daily simply doesn't count that
  day, and a saved daily token is rejected once its date has passed (mirrors the
  Wordle daily date gate). **Freeplay** is a random round with the player's
  chosen deck / difficulty / answer mode and may be ended any time.
- **Daily anti-harvest.** Like the conjugation daily, per-card feedback
  **withholds the answer in daily mode** — the client gets no per-card
  feedback at all (not even the `exact`/`close`/`wrong` flag), and the running
  `correct`/`streak`/`best_streak` counters are withheld (`null`) too. Because
  the daily's state round-trips as a replayable sealed token, exposing even the
  result flag or the score would let a choice-mode player replay the previous
  turn's token against each of the 4 options and read the answer off of which
  one moves the flag/score. Everything — per-card result, the correct word, and
  the running score — is disclosed only in the end-of-round recap. Freeplay
  reveals both normally (no streak stakes, nothing to game).
- **Streak boundary: attendance, not enforced effort.** The daily streak (like
  every daily game here) measures that the player **completed** a round, not
  that they tried. `result_payload` marks a finished daily `won: True`
  unconditionally — a player who submits 10 junk-but-non-empty guesses still
  banks a `won=True` `0/10` and the streak bump, same as someone who answered
  well. Only a truly *empty* guess is rejected (`submit`'s empty-guess guard);
  anything non-empty grades as `wrong` and advances. Closing this would need
  server-side per-guess attempt consumption (see the honor-system limit above)
  — a cost deliberately not paid for a cosmetic streak. This is a documented,
  accepted boundary, not a bug: the stateless design can't distinguish "tried
  and missed" from "mashed junk to finish" without that added cost.

### Persistence

The Activity backend opens its **own asyncpg pool** to the same Postgres the
bot uses (`DATABASE_URL`). Tables are game-agnostic, keyed by `game_key`:
`game_results` (one row per finished game, `posted_at` NULL until the Phase 2
bot posts it) and `game_stats` (per-user daily aggregates + streak +
guess-distribution). The Activity creates these idempotently on boot. If
`DATABASE_URL` is unset the game still plays; stats just read as zeros.

The daily-result insert and the streak/stats bump run in **one transaction**
(`record_result`), so a mid-write failure can't leave the unique daily row
committed while the streak update is lost (which would permanently block the
retry that fixes it). Request fields (`access_token`, `sealed_state`, `guess`)
are length-bounded at the Pydantic layer so an oversized body is rejected
before any Fernet/normalization work.

## Developer Portal setup (one-time)

Use the **existing Hablemos application** (shared `CLIENT_ID`; the bot is
already in the guild). At <https://discord.com/developers/applications> →
your app:

1. **Activities → Settings → "Enable Activities."** This auto-creates the
   Entry Point ("Launch") command.
2. **Activities → URL Mappings.** Add a root mapping:
   - Prefix: `/`  →  Target: your host **without** `https://`
     (the cloudflared tunnel host in dev, the Railway domain in prod).
   - The target must be a **directory, not a file**. If you add more specific
     prefixes later, list them **longest-first**.
3. **OAuth2 → Redirects.** Add at least one redirect URI or `authorize()`
   fails. `https://127.0.0.1` is fine for dev (the SDK handles the redirect
   internally).
4. **Installation / Supported Platforms.** Enable the platforms (Web / iOS /
   Android) you want the Activity to appear on.
5. Copy the **Client ID** (safe to ship in the frontend) and generate/copy the
   **Client Secret** (server-only — never in the frontend bundle).

## Local development

The Activity must load over HTTPS in Discord's iframe, so you need a public
tunnel to your local machine.

```bash
# 1. Backend (FastAPI) — from activity/backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env          # fill in DISCORD_CLIENT_ID + DISCORD_CLIENT_SECRET
uvicorn app.main:app --reload --port 8080

# 2. Frontend (Vite) — from activity/frontend, in another shell
npm install
echo "VITE_DISCORD_CLIENT_ID=<your client id>" > .env
npm run dev                      # serves on :5173, proxies /.proxy/api → :8080

# 3. Tunnel the Vite dev server — in a third shell
cloudflared tunnel --url http://localhost:5173
```

Then paste the `https://…trycloudflare.com` host into the Developer Portal
**URL Mapping** (root `/`) and as an OAuth **redirect**. Enable Developer Mode
in Discord and launch the Activity from a voice channel's activity shelf.

> Ephemeral `trycloudflare.com` URLs change on every restart, which means
> re-pasting the mapping each session. Set up a **named** cloudflared tunnel
> with a stable hostname to avoid the churn.

In dev the Vite server ([`vite.config.ts`](../activity/frontend/vite.config.ts))
proxies both `/.proxy/api/*` and `/api/*` to the FastAPI backend, so the same
`fetch("/.proxy/api/…")` code works locally and in Discord.

## Production deploy (Railway)

The Activity is **one new web service** in the existing Railway project. A
single [`Dockerfile`](../activity/Dockerfile) builds the SPA (Node stage) and
runs FastAPI serving both the static `dist/` and `/api/*` (Python stage), so
it's one HTTPS origin — no CORS, no cross-origin cookies.

```bash
# From activity/ — requires an authenticated Railway CLI (railway login,
# or export RAILWAY_TOKEN=… from railway.com/account/tokens).
railway service create hablemos-activity     # or create it in the dashboard
railway up --service hablemos-activity        # build + deploy the Dockerfile
```

Set these as **service variables** on the new service (see the env table in
[`deployment.md`](./deployment.md#activity-embedded-app)):

- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` — runtime (backend).
- `VITE_DISCORD_CLIENT_ID` — **build-time** arg; Vite inlines it into the
  client bundle. On Railway, set it as a service variable and reference it in
  the build (the Dockerfile declares the `ARG`).

Once deployed, take the service's public domain
(`hablemos-activity.up.railway.app`, or a custom domain) and set it as the
production **URL Mapping** root target in the Developer Portal (no `https://`
prefix). The `PORT` env var is provided by Railway automatically.

## Verifying the handshake

The plumbing is covered by a local smoke test (routes + static serving). The
full OAuth handshake can only be confirmed live inside Discord:

1. Launch the Activity from a voice channel.
2. It should briefly show "Conectando con Discord…" then render
   "¡Hola, `<your name>`! 👋" with your avatar.
3. If it shows an error, open the in-client devtools console (Developer Mode)
   and check for `blocked:csp` (a URL Mapping / `/.proxy` issue) or a 502 from
   `/api/token` (wrong `DISCORD_CLIENT_SECRET`).

See [`playbook.md`](./playbook.md) for the failure-mode runbook.
