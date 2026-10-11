# Bot token was reset or is wrong

**When:** the logs show `Discord rejected the bot token` or
`LoginFailure: Improper token has been passed`.
**Last verified:** 2026-10-11

## Cause

`BOT_TOKEN` is wrong or was reset. Discord resets a token by itself when the bot
logs in more than 1000 times in a short period, usually a crash loop. It sends a
DM from "Discord" to the app owner with a link to the bot page. Resetting the
token by hand in the Developer Portal has the same effect.

## Steps

1. Fix the cause of any crash loop first (`intents-rejected.md`), or the token
   resets again.
2. Developer Portal → the app → **Bot** → **Reset Token**. Copy the new token.
3. Store it from your own terminal. The command prompts for the value, so the token
   stays out of shell history, chats and commits:
   ```bash
   gh secret set BOT_TOKEN
   ```
4. Redeploy the bot (`deploy.md`). A deploy reads the secret when its job starts:
   ```bash
   gh workflow run deploy-lightsail.yml -f deploy_activity=false -f deploy_logforwarder=false
   ```

## Verify

The logs show `Shard ID None has connected to Gateway`.
