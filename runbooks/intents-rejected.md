# Discord rejects the privileged intents

**When:** the logs show `Discord rejected the privileged intents` or
`PrivilegedIntentsRequired`, and the bot is offline.
**Last verified:** 2026-10-11

## Cause

`hablemos.py` requests three privileged intents: `members`, `message_content`
and `presences`. Discord rejected at least one. Either someone switched a toggle
off, or Discord removed access after a review. Since 2026-06-10 an app that more
than 10,000 unique users can see must apply for these intents, and an app with
access must reapply every year. Discord sends a portal notice, then allows 90
days. Missing the window removes access, and the portal then shows a **Request
Intents** form instead of toggles. Source:
<https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review>

`cogs/utils/login_guard.py` catches the rejection, logs one error, waits 30
minutes and exits. That caps the retries at about 48 a day. Without it, the
restart loop passes 1000 logins a day, and Discord resets the bot token
(`token-reset.md`).

## Steps

1. Open the Developer Portal → the app → **Bot** → **Privileged Gateway Intents**.
2. **Toggles shown:** switch on the intents you need, save, and wait for the next
   restart (within 30 minutes) or re-run the last deploy (`deploy.md`).
3. **Request Intents form shown:** submit it. Request only intents you can show
   the bot needs. Discord rejects weak reasons.
   - Privacy policy URL: `PRIVACY.md` in this repo, linked from the portal.
   - Deletion contact: `/deletemydata` (`delete-user-data.md`).
   - Screenshots: leaderboard, a game, a `$` command, `/deletemydata`.
4. **Need the bot back now:** create a new app (`new-discord-app.md`). A new app can
   switch intents on without review until it passes 10,000 users. Then it has 90
   days from the notice to apply.
5. **Last resort:** drop the unapproved intent in `hablemos.py` and redeploy:
   - `presences`: only `spotify_cog` (opt-in `$spotify on`) reads activities.
   - `members`: many `guild.get_member` lookups (League roles, stats, names in
     `cogs/utils/names.py`).
   - `message_content`: every `$` command and the `on_message` trackers. Slash
     commands keep working without it.

## Verify

The logs show `Shard ID None has connected to Gateway`.
