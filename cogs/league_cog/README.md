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
├── views.py     # Persistent "Join the League" button
├── config.py    # IDs, scoring, rate limits, round and display settings
└── league_helper/
    ├── leaderboard_image_pillow.py  # /league view image
    ├── round_end_image.py           # Round-end podium image
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
- `/league stats [user]`

## Scoring

A message counts when the author is opted in and not banned, the channel isn't excluded, the
per-channel 30-second cooldown has passed, and `cogs/utils/language.py` detects the language the
author is learning (at least 10 characters after removing emojis, confidence 0.8). At most 200
counted messages per user per UTC day; only messages that would score use up the cap.

Score = points + 5 × active days in the round. Beginner channels (`LEAGUE_BEGINNER_CHANNEL_IDS`)
give 2 points per message instead of 1. Boards order by score descending, then user ID ascending.

Cooldowns and daily counts are kept in memory and reset on restart.

## Rounds

`check_round_end` runs every minute. When the active round's end date passes, `process_round_end`:

1. Reads the boards and picks the champions: the top 3 per board, skipping anyone who held the
   role last round.
2. In one transaction (`complete_round`): saves the top 3 per board to `league_round_winners`,
   records the champions in `league_role_recipients`, marks the round completed, and creates the
   next round. If the round was already completed, nothing changes and it returns `None`.
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
