# Deployment (AWS Lightsail)

Both services live in this monorepo and deploy to Lightsail container services
in `us-east-1`:

| Service | Lightsail service name | Build context | Public? |
|---|---|---|---|
| Activity (FastAPI + Vite SPA) | `hablemos-activity` | `activity/` | Yes (HTTPS) |
| Discord bot | `hablemos-discordpy-bot` | repo root | No (worker) |

Managed Postgres: `hablemos-postgres` (private endpoint, reached via `DATABASE_URL`).

## CI/CD

`.github/workflows/deploy-lightsail.yml` builds and deploys on push to `main`.
Path filters mean an `activity/**` change only redeploys the activity, and a
root change only redeploys the bot. Use the **Run workflow** button
(workflow_dispatch) to force either or both.

The deploy logic is in `scripts/lightsail_deploy.sh`: push image →
`create-container-service-deployment` → poll until `ACTIVE`.

Container env config lives in `deploy/*.containers.json` with `${VAR}`
placeholders. CI fills them via `envsubst` from GitHub secrets — **no secrets
are committed**. The `__IMAGE__` placeholder is replaced by the deploy script
with the ref returned by `push-container-image`.

## Required GitHub secrets

Set these in the repo: Settings → Secrets and variables → Actions.

### Deploy credentials (the IAM identity that runs Lightsail commands)
| Secret | Notes |
|---|---|
| `DEPLOY_AWS_ACCESS_KEY_ID` | IAM user with Lightsail push/deploy permissions. |
| `DEPLOY_AWS_SECRET_ACCESS_KEY` | " |

### Shared
| Secret | Value source |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:<pw>@<lightsail-endpoint>:5432/railway?sslmode=require` |

### Activity
| Secret |
|---|
| `DISCORD_CLIENT_ID` |
| `DISCORD_CLIENT_SECRET` |

### Bot
| Secret |
|---|
| `BOT_TOKEN` |
| `GEMINI_API_KEY` |
| `ACTIVITY_RESULTS_CHANNEL_ID` |
| `TICKETSUB_MIN_ROLE_ID` |
| `WCBET_AUTO_SETTLE` |
| `LOG_WEBHOOK_URL` |
| `APP_AWS_ACCESS_KEY_ID` | The bot's *own* AWS key (distinct from the deploy key). |
| `APP_AWS_SECRET_ACCESS_KEY` | " |

> The bot's runtime AWS creds are prefixed `APP_` so they don't collide with the
> deploy-role creds in the runner environment.

## Set secrets fast with the gh CLI

```bash
gh secret set DATABASE_URL --repo Jaleel-VS/hablemos-discordpy-bot
# ...repeat per secret, or script it from a local .env (do NOT commit that file)
```

## Manual deploy from a laptop

```bash
# Build (must be linux/amd64 — Lightsail runs amd64):
docker build --platform linux/amd64 -t hablemos-bot:local .
docker build --platform linux/amd64 --build-arg VITE_DISCORD_CLIENT_ID=<id> -t hablemos-activity:local activity/

# Render config (export the same vars first), then deploy:
envsubst < deploy/bot.containers.json > /tmp/bot.containers.json
AWS_REGION=us-east-1 scripts/lightsail_deploy.sh hablemos-discordpy-bot hablemos-bot:local /tmp/bot.containers.json
```

## Slash command sync

Global slash commands are not auto-synced. After a deploy that adds/changes
global commands, run `$sync` as the bot owner (see `docs/deployment.md`).
