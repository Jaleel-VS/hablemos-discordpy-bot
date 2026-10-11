# Deploy, re-run or roll back

**When:** shipping a change, re-running a failed deploy, or rolling back.
**Last verified:** 2026-10-11

Pipeline, secrets and manual laptop deploys: `deploy/README.md`.

## Steps

1. **Ship:** push to `main`. `.github/workflows/deploy-lightsail.yml` deploys only
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
  `FAILED` deploy leaves the old version running.
- A push during a manual run queues. Deploys of the same ref never overlap.
- A bot that exits on a rejected login (`cogs/utils/login_guard.py`) waits 30
  minutes first, so it still counts as running and the deploy goes `ACTIVE`.

## Verify

State is `ACTIVE`. The logs (see `read-logs.md`) show `Shard ID None has connected to Gateway`
and one `Loaded extension:` line per enabled cog.
