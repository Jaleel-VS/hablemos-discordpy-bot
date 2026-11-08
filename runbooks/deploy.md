# Deploy, re-run or roll back

**When:** shipping a change, re-running a failed deploy, or rolling back.
**Last verified:** 2026-11-08

Pipeline, secrets and manual laptop deploys: `deploy/README.md`.

## Steps

1. **Ship:** push to `main`. `.github/workflows/deploy-lightsail.yml` first runs
   the Tests workflow (bot suite with Postgres, Activity backend, frontend
   typecheck); a red test blocks every deploy job. It then deploys only
   the services whose files changed (bot: `cogs/`, `db/`, the root Python files,
   `pyproject.toml`, `Dockerfile`, `deploy/bot.containers.json`; Activity:
   `activity/**`; log forwarder: `logforwarder/**`). Tests and runbooks don't deploy.
2. **Run by hand** (for example after changing a secret). Inputs are
   `deploy_bot`, `deploy_activity` and `deploy_logforwarder`:
   ```bash
   gh workflow run deploy-lightsail.yml -f deploy_activity=false -f deploy_logforwarder=false
   ```
3. **Re-run a failed run:** `gh run rerun <run-id> --failed`. A re-run reads the
   current secrets.
4. **Watch:** `gh run watch <run-id> --exit-status`.
5. **Roll back:** `AWS_REGION=us-east-1 scripts/lightsail_rollback.sh <service> [version]`.
6. **New global slash commands:** run `$sync` as the owner. Prefix commands need nothing.

## Gotchas

- The deploy script polls for about 6.7 minutes (40 checks, 10 s apart). Lightsail
  sometimes needs longer, so a red run can still end `ACTIVE`. Check:
  ```bash
  aws lightsail get-container-service-deployments --region us-east-1 \
    --service-name hablemos-discordpy-bot --query 'deployments[:3].[version,state]' --output text
  ```
- Lightsail keeps the previous version serving until the new one is healthy. A
  `FAILED` deploy leaves the old version running, unless the new bot already
  reached the gateway: then the old bot has handed over (below) and idles, so the
  bot is offline until you roll back.
- Only one bot holds the Discord session (`cogs/utils/instance_guard.py`). Each
  deployment gets `DEPLOY_VERSION` = its creation time from `scripts/lightsail_deploy.sh`
  (rollbacks restamp it). The new bot claims the session on gateway connect and the old
  one logs `took over the bot session`, then idles until Lightsail stops it. A
  deployment edited by hand in the Lightsail console keeps its old version and will
  refuse to start; deploy through the scripts instead. `$deploys` (owner) lists the
  handovers, including `overlap_seconds`.
- `ThrottlingException` on `CreateContainerServiceDeployment` means several
  services deployed at once hit the Lightsail API rate limit. Re-run the failed job.
- A push during a manual run queues. Deploys of the same ref never overlap.
- A bot that exits on a rejected login (`cogs/utils/login_guard.py`) waits 30
  minutes first, so it still counts as running and the deploy goes `ACTIVE`.
- The Docker base images' Python (`FROM python:3.12-…` in `Dockerfile`, `activity/Dockerfile`,
  `logforwarder/Dockerfile`) must match `requires-python` in each `pyproject.toml`. A mismatch
  fails the image build with `No interpreter found for Python ==3.12.*` while tests stay green
  (they don't run in the image). Dependabot's 3.15 bump did this on 2026-11-08; it now skips
  Python major/minor image bumps (`.github/dependabot.yml`), so upgrade both together by hand.

## Verify

State is `ACTIVE`. The logs (see `read-logs.md`) show `Shard ID None has connected to Gateway`,
`claimed the bot session`, and one `Loaded extension:` line per enabled cog.
