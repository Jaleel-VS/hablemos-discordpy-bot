# Hablemos Activity

A [Discord Activity](https://docs.discord.com/developers/activities/overview) —
an embedded web app that runs inside Discord — hosting Spanish-language games
(starting with a Spanish Wordle). It is a **separate Lightsail container
service** from the gateway bot; the two share the same PostgreSQL database.

- **Frontend** (`frontend/`) — Vite + React + TypeScript, using
  `@discord/embedded-app-sdk`. Runs inside Discord's sandboxed iframe.
- **Backend** (`backend/`) — FastAPI. Handles the OAuth2 token exchange
  (keeping `client_secret` server-side), authoritative game logic, and writes
  results to Postgres. Also serves the built SPA (`frontend/dist/`) so the
  whole Activity is one service + one HTTPS origin.

The gateway bot (unchanged) polls a results table and posts finished-game
cards to a configured channel.

## Layout

```
activity/
  frontend/          Vite + React + TS SPA (@discord/embedded-app-sdk)
    src/
    package.json
    vite.config.ts
  backend/           FastAPI app
    app/
      main.py        app factory, static serving, routers
      config.py      env config (mirrors root config.py helpers)
      discord_oauth.py  token exchange + users/@me verification
    pyproject.toml   deps (uv); uv.lock pins them
  Dockerfile         builds SPA, then runs FastAPI serving dist/ + /api
```

## Why this shape

The frontend *must* be browser JS/TS — it runs in Discord's iframe. The
backend can be any language, so it's Python/FastAPI to reuse the bot's
`asyncpg` pool, config conventions, and Postgres. One service serving both
the static SPA and `/api/*` avoids CORS and cross-origin cookie problems
inside Discord's proxy.

## The Discord proxy (the #1 gotcha)

Everything the iframe fetches is routed through
`https://<CLIENT_ID>.discordsays.com` with a strict CSP. **Every** backend
call from the SPA must go through the `/.proxy/` prefix (e.g.
`fetch("/.proxy/api/token")`) and be declared in the app's URL Mappings, or
it silently fails with `blocked:csp`.

## Outpost engine and simulator (Phase 0)

`backend/app/outpost/` holds the engine for *Outpost*, the async strategy
game designed in [`plans/outpost.md`](../plans/outpost.md). It isn't wired
into any route yet.

- `rules/`: `Params` (every tunable knob) and `v1.py` (the §6 numbers).
  The integer level tables are generated from these once per `Params`.
- `engine/`: deterministic integer-math engine (`core.Engine` over a
  mutable `state.World`) and fixed-point combat (`combat.py`).
- `sim/`: agents, the round runner, parameter sweeps, the evolutionary
  strategy search, MAP-Elites, the SQLite results store and an HTML
  dashboard. Agents explore within a round: they sample choices instead of
  always taking the best-looking one, learn which raid targets pay, adjust
  army spending day by day (`learning.py`), and can send fakes, gang up on
  an alliance target, and dodge attacks by moving their army out.

Run these from `activity/backend` with the repo-root venv (it has pytest):

```sh
python -m app.outpost.sim run --seed 1 --trace          # one round
python -m app.outpost.sim sweep --grid bucket_hours=2,4,8 \
    --grid vault_pct=5,10,20 --seeds 1,2,3              # grid sweep
python -m app.outpost.sim sweep --random monument_base=50000:300000 --n 20
python -m app.outpost.sim evolve --generations 8 --population 12
python -m app.outpost.sim map --x loot_share --y army_frac   # strategy map
python -m app.outpost.sim --set speed_pct=200 run       # override base params
TYPESAFE_API_KEY=... python -m app.outpost.sim run --judge   # Jev experience
TYPESAFE_API_KEY=... python -m app.outpost.sim sweep --grid bucket_hours=2,4,8 --judge
TYPESAFE_API_KEY=... python -m app.outpost.sim run --jev 4       # 4 Jev players
```

Every command writes to `sim_out/` (gitignored): `results.sqlite`,
`traces/` (replays) and `report.html`, a self-contained dashboard with
sweep heatmaps, archetype power curves, invariant checks, evolution
fitness, the strategy map (best strategy per style of play) and a map
replay. A round of 40 agents takes about 1 s; sweeps, evolution and
MAP-Elites use every CPU core.

`--judge` sends each player's round diary (ranks, raids suffered, losses,
wins, evacuations, alliance outcome; never their archetype or whether they
quit) to TypeSafe's Jev model, which scores frustration, quit risk,
perceived unfairness and pride (`sim/experience.py`). Results land in
`player_experience` and as `exp_*` run metrics, so they show in the sweep
table and heatmaps. One request per player; a 40-player round takes ~3 s.

`--jev N` adds N players whose key calls Jev makes (`sim/jev.py`). Code
still builds, trains and scores every legal option with the real combat
rules; once per in-game day Jev picks a troop-spending stance and a focus
(grow, expand or fortify), and at each check-in it picks a raid target
from the top five (or none) and decides whether to evacuate before an
incoming attack. Answers are cached in `sim_out/jev_cache.sqlite`, so
rerunning a seed replays with no API calls. A fresh round with 4 Jev
players makes about 350 calls and takes ~2.5 min; a replay takes ~1 s.

Tests: `pytest tests/test_outpost_*.py`.
