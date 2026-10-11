# Language League: round end or leaderboard looks wrong

**When:** a round ended but nothing was announced, scores look stale, or the bot was down over a round end.
**Last verified:** 2026-10-11

## How it works

`check_round_end` (`cogs/league_cog/main.py`) runs every minute, reads the current round
from the database, and processes it when `now >= end_date`. It posts to the winner channel
(`LEAGUE_WINNER_CHANNEL_ID`), moves the champion role, and creates the next round starting
**now**. After downtime, the first check after startup processes the missed round late.
It never replays several rounds.

## Steps

1. **No announcement:** search the logs for `check_round_end` and `Round .* has ended`
   (`read-logs.md`). Usual causes: the winner channel ID is wrong or the bot can't post
   there; the guild or champion role can't be fetched; a database error in the round-end step.
2. Fix the cause, then run `$league endround` (owner). It processes the round, assigns the
   roles and posts the announcement.
3. Before a round ends, `$league preview` is a dry run with no changes.
4. **Stale leaderboard:** it is cached for 30 seconds (`LEADERBOARD_CACHE_TTL`). Counted
   messages clear the cache. SQL edits don't. Wait 30 seconds or restart the bot.
5. **Roles not moving:** the bot's role must sit above the champion role and have Manage
   Roles (`new-discord-app.md`, step 6).

## Verify

The announcement is in the winner channel, and the logs show `Created next round`.
