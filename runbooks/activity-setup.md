# Set up or debug the Discord Activity

**When:** enabling the Activity on an application, running it locally, or a launch fails.
**Last verified:** 2026-10-11 (ported from the old docs; the portal steps were not re-run)

Code: `activity/` (FastAPI backend in `activity/backend`, Vite SPA in `activity/frontend`).
It is the `hablemos-activity` Lightsail service. The bot launches it from `$wordle` and
`$conjuga` buttons (`cogs/utils/activity_launch.py`). No voice channel is needed.

## Portal setup (once per application)

1. **Activities → Settings → Enable Activities.** This creates the Entry Point ("Launch") command.
2. **Activities → URL Mappings.** Root mapping: prefix `/`, target = the host **without**
   `https://` (the Lightsail service domain in production, the tunnel host in development).
   The target is a directory, not a file. List any longer prefixes first.
3. **OAuth2 → Redirects.** Add at least one, such as `https://127.0.0.1`, or `authorize()` fails.
4. **Installation / Supported Platforms.** Tick Web, iOS and Android as needed.
5. Copy the **Client ID** (public) and the **Client Secret** (server only).
   GitHub secrets: `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` (`deploy/README.md`).

While the app is unpublished, it only shows in the Activity Shelf for the owner or team
members with Developer Mode on. A first launch shows a "not made by Discord" prompt.

## Local development

```bash
# backend: from activity/backend
uv sync && cp ../.env.example .env      # set DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET
uv run uvicorn app.main:app --reload --port 8080
# frontend: from activity/frontend, another shell
npm install && echo "VITE_DISCORD_CLIENT_ID=<id>" > .env && npm run dev
# tunnel: a third shell, then paste the host into the URL Mapping and a redirect
cloudflared tunnel --url http://localhost:5173
```

Quick tunnels change on every restart. A named tunnel avoids re-pasting the mapping.

## Gotchas

- **Every backend call from the SPA needs the `/.proxy/` prefix** (`fetch("/.proxy/api/token")`)
  and a URL Mapping, or it fails silently with `blocked:csp`. Discord strips `/.proxy`, so
  the FastAPI routes have no prefix.
- `VITE_DISCORD_CLIENT_ID` is a **build-time** value. Changing it needs a rebuild and deploy.
- A global `$sync` can fail with error 50240 because of the Entry Point command. `$sync`
  then falls back to a guild sync (`runbooks/new-discord-app.md`).

## Verify

Launch it. It shows "Conectando con Discord…", then "¡Hola, <name>!" with your avatar. If
it errors, open the client devtools: `blocked:csp` means a URL Mapping or `/.proxy` problem;
a 502 from `/api/token` means a wrong `DISCORD_CLIENT_SECRET`.
