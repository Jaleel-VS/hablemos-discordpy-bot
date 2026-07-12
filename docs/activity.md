# Discord Activity (embedded games)

The bot has a companion **Discord Activity** — an embedded web app that runs
inside Discord's client (the same mechanism as YouTube Watch Together or the
official word games). It hosts Spanish-language games; the first is a Spanish
Wordle. When a daily game finishes, the result posts to a configured channel.

The Activity is a **separate Railway web service** from the gateway bot. They
share the same PostgreSQL database. The code lives in
[`../activity/`](../activity/) (see its
[`README.md`](../activity/README.md) for the internal layout).

> **Status:** Phases 0–2 built. Phase 0 (OAuth handshake) is live in
> production. Phase 1 is the extensible game framework with **Spanish Wordle**
> (daily + freeplay, stats/streaks in the shared Postgres). Phase 2 is the bot
> posting finished **daily** results to a configured channel.

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

### Launching (testing an unpublished Activity)

Activities launch from the **voice-channel Activity Shelf** (the 🚀 Rocket
button in a voice channel), *not* from the app's profile card. While the app is
unpublished it only appears in the shelf for the **owner account** (or team
members) with **Developer Mode** on and the tested **platform** checked under
Activities → Supported Platforms. A first launch shows a "not made by Discord"
confirmation — expected for a private test app. Your bot can also launch it
from a command later via the `LAUNCH_ACTIVITY` interaction callback (Phase 2+).

## Games framework (Phase 1)

The backend is a small **registry over a game-engine contract**, so adding a
game touches only its own module:

- `app/games/base.py` — the `GameEngine` protocol
  (`new_game` / `submit` / `is_over` / `result_payload`) and shared types.
- `app/games/registry.py` — the one place that lists games. Add a game = add
  one line here.
- `app/games/routes.py` — generic routes for **every** game:
  `POST /api/games/{key}/start`, `/guess`, `/stats`, and `GET /api/games`.
- `app/games/wordle/` — the first game (see below).

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

### Persistence

The Activity backend opens its **own asyncpg pool** to the same Postgres the
bot uses (`DATABASE_URL`). Tables are game-agnostic, keyed by `game_key`:
`game_results` (one row per finished game, `posted_at` NULL until the Phase 2
bot posts it) and `game_stats` (per-user daily aggregates + streak +
guess-distribution). The Activity creates these idempotently on boot. If
`DATABASE_URL` is unset the game still plays; stats just read as zeros.

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
