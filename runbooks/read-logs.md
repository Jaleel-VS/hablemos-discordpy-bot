# Read production logs

**When:** you need to see what a service is doing, or why a deploy or the bot failed.
**Last verified:** 2026-10-11

Authenticate to AWS first (profile `Jaleel`, region `us-east-1`).

## Steps

1. List services: `python scripts/lightsail_logs.py --discover`.
2. Pull logs. The default service is `hablemos-discordpy-bot`:
   ```bash
   python scripts/lightsail_logs.py --limit 1000 --filter ERROR
   python scripts/lightsail_logs.py --service hablemos-activity --json
   ```
3. If the script hangs or fails, call the API directly. The container name is `app`:
   ```bash
   aws lightsail get-container-log --region us-east-1 \
     --service-name hablemos-discordpy-bot --container-name app \
     --start-time <epoch-seconds> --query 'logEvents[].[createdAt,message]' --output text
   ```
   Epoch seconds: `date -u -d '10 minutes ago' +%s` (GNU) or `date -u -v-10M +%s` (macOS).

## Gotchas

- The API returns events **oldest first**, about 100 per page. To see the latest
  lines, use a narrow `--start-time` window or follow `nextPageToken`.
- Lightsail keeps about 3 days. Longer history is in Axiom (`logforwarder/`).
- During a deploy, the old and new containers both log. Check the timestamps.
- `ExpiredTokenException` means the AWS credentials expired. Authenticate again.

## Verify

The newest line is minutes old, and it comes from the container you expect.
