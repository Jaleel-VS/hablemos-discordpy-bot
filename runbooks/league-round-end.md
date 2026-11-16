# Language League: round end or leaderboard looks wrong

**When:** a round ended but nothing was announced, scores look stale, or the bot was down over a round end.
**Last verified:** 2026-11-16

## How it works

`check_round_end` (`cogs/league_cog/main.py`) runs every minute, reads the current round
from the database, and processes it when `now >= end_date` (`process_round_end` in
`cogs/league_cog/rounds.py`). First, one transaction saves the winners and champion holders,
marks the round completed and creates the next round, starting **now** and ending the next
Sunday at 12:00 UTC. Only then does it move the champion role and post to the winner channel
(`LEAGUE_WINNER_CHANNEL_ID`). After downtime, the first check after startup processes the
missed round late. It never replays several rounds, and a round can't be processed twice.

## Steps

1. **No announcement:** search the logs for `check_round_end` and `Round .* has ended`
   (`read-logs.md`). If the logs show `Created next round`, the database step succeeded and
   only the role move or the announcement failed. Usual causes: the winner channel ID is
   wrong or the bot can't post there; the guild or champion role can't be fetched.
2. Fix the cause. **Don't** run `$league endround` for a round that already shows
   `Created next round`: it ends the new round. Post the result and move the role by hand;
   the winners are in `league_round_winners` and the role holders in
   `league_role_recipients` for that `round_id`.
3. If the logs show a database error and no `Created next round`, nothing was written. Fix
   the cause; the next minute's check retries, or run `$league endround` (owner).
4. Before a round ends, `$league preview` is a dry run with no changes.
5. **Stale leaderboard:** `/league view` is cached for 30 seconds (`LEADERBOARD_CACHE_TTL`);
   only a round end clears it early. Wait 30 seconds or restart the bot.
6. **Roles not moving:** the bot's role must sit above the champion role and have Manage
   Roles (`new-discord-app.md`, step 6).

## Verify

The announcement is in the winner channel, and the logs show `Created next round`.
