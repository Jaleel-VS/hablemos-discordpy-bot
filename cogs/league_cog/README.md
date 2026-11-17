# Language League Cog

A weekly competition for language learners. Opted-in members score points for messages written in
the language they are learning, and the top scorers of each round get the champion role.

## Layout

```
cogs/league_cog/
├── main.py      # LeagueCog: /league slash commands, message scoring, round check task
├── admin.py     # LeagueAdminCog: owner-only $league group and $langa
├── rounds.py    # Round end: winners, next round, champion role, announcement
├── scoring.py   # Points per counted message (beginner-channel multiplier)
├── levels.py    # Level curve, level-up detection, background tiers
├── views.py     # Persistent "Join the League" button
├── config.py    # IDs, scoring, rate limits, round and display settings
└── league_helper/
    ├── leaderboard_image_pillow.py  # /league view image
    ├── round_end_image.py           # Round-end podium image
    ├── level_card_image.py          # Level-up card and /league profile card
    ├── level_backgrounds/           # One background per tier (generated, committed)
    ├── topchannels_image.py         # $league topchannels image
    └── heatmap_image.py             # $league heatmap image
```

Database queries live in `db/leaderboard.py` (`LeaderboardMixin`); tables are created in
`db/schema.py`. `main.py`'s `setup()` loads both cogs.

## User commands

- `/league join` (or the join button): needs exactly one learning role, and not the native role
  for that language. The board (Spanish or English) is fixed at join time.
- `/league leave`
- `/league view [spanish|english|combined]`: top 10 as an image, cached for 30 seconds.
- `/league profile [user]`: one card with the level and progress bar, this round (board and
  combined rank, movement since last round, score, active days, gap to the next rank) and history
  (streak, podiums, champion weeks, best round, last 7 days).
- `/league levelups on|off`: level-up cards on or off; the level keeps counting either way.

## Scoring

A message counts when the author is opted in and not banned, the channel isn't excluded, the
per-channel 30-second cooldown has passed, and `cogs/utils/language.py` detects the language the
author is learning (at least 10 characters after removing emojis, confidence 0.8). At most 200
counted messages per user per UTC day; only messages that would score use up the cap.

Score = points + 5 × active days in the round. Beginner channels (`LEAGUE_BEGINNER_CHANNEL_IDS`)
give 2 points per message instead of 1. Boards order by score descending, then user ID ascending.

Cooldowns and daily counts are kept in memory and reset on restart.

## Levels

Every counted message also adds its points to the author's level XP (`league_levels`), in the
same transaction that records it, so a level-up is detected exactly once. XP counts from launch
(2026-11-16) with no backfill, and survives leaving the league and round ends.

Reaching level `L` takes `25 × (L − 1)^1.5` total XP (`LEVELS` in `config.py`): level 10 at
about 700, 50 at about 8,600, 100 at about 24,600. When a message crosses a threshold, the bot
posts a level-up card in that channel, naming the author without pinging them, unless the author
turned cards off.

Cards use the tier's background: Dawn 1–9, Mist 10–24, Lilac 25–49, Tide 50–74, Bloom 75–99,
Gold 100+ (`TIERS` in `levels.py`). The backgrounds come from Stable Image Core on Bedrock;
`scripts/generate_level_backgrounds.py [tier ...]` regenerates them.

## Profile and card language

Cards are in the language the reader is learning: Spanish for members with only the
learning-Spanish role, English otherwise (`card_text.py`). The level-up card follows its author's
roles; `/league profile` follows the viewer's.

`leaderboard_activity` is purged two rounds back (`purge_old_league_activity`), so lasting stats
are stored as they happen:

- `league_round_results`: every participant's final rank and score per board, saved in the
  round-end transaction. Rank movement and best round read it. It starts with the first round to
  end after this launch; best round also counts podium scores from `league_round_winners`.
- Streaks live in `league_levels` (current, best, last active UTC day), updated with each counted
  message, from launch. A streak shows as 0 once a whole UTC day passes without activity.
- Podiums and champion weeks come from `league_round_winners` and `league_role_recipients`,
  which go back to the first round.

## Rounds

`check_round_end` runs every minute. When the active round's end date passes, `process_round_end`:

1. Reads the boards and picks the champions: the top 3 per board, skipping anyone who held the
   role last round.
2. In one transaction (`complete_round`): saves the top 3 per board to `league_round_winners`,
   records the champions in `league_role_recipients`, marks the round completed, and creates the
   next round. If the round was already completed, nothing changes and it returns `None`.
   Once it commits, new messages score into the next round.
3. Moves the champion role and posts the announcement with the podium image. Failures here are
   logged and don't affect the database state.

Rounds end on Sunday at 12:00 UTC; a round started on a Sunday runs to the next Sunday.

## Admin commands (owner only)

| Command | Purpose |
|---|---|
| `$league ban/unban <user>` | Ban or unban; banning works for users who never joined |
| `$league exclude/include <#channel>`, `$league excluded` | Channel exclusions |
| `$league validatemessage <link>`, `$langa <text\|link>` | Debug language detection |
| `$league admin_stats` | User and message counts |
| `$league audit <user>` | Last 3 counted messages |
| `$league endround`, `$league preview` | End the round now; dry run of the result |
| `$league seedrole <ids>` | Seed last round's champion holders |
| `$league topchannels [days]`, `$league heatmap [days]`, `$league recent [n]` | Activity reports |
| `$league reminder [#channel]` | Post the join reminder with the button |

Round-end troubleshooting: `runbooks/league-round-end.md`.
