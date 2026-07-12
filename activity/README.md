# Hablemos Activity

A [Discord Activity](https://docs.discord.com/developers/activities/overview) —
an embedded web app that runs inside Discord — hosting Spanish-language games
(starting with a Spanish Wordle). It is a **separate Railway web service** from
the gateway bot; the two share the same PostgreSQL database.

- **Frontend** (`frontend/`) — Vite + React + TypeScript, using
  `@discord/embedded-app-sdk`. Runs inside Discord's sandboxed iframe.
- **Backend** (`backend/`) — FastAPI. Handles the OAuth2 token exchange
  (keeping `client_secret` server-side), authoritative game logic, and writes
  results to Postgres. Also serves the built SPA (`frontend/dist/`) so the
  whole Activity is one service + one HTTPS origin.

The gateway bot (unchanged) polls a results table and posts finished-game
cards to a configured channel.

See [`../docs/activity.md`](../docs/activity.md) for the full setup guide
(Discord Developer Portal config, local dev tunnel, Railway deploy).

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
    requirements.txt
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
