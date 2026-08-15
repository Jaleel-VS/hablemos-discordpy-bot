# Stats Cog

Owner-only analytics for the main Hablemos guild. The cog tracks non-bot
messages in the configured stats guild and writes hourly aggregate counts
instead of storing message content.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$stats [days]` | Activity summary: top channels, messages by native-role type, total users, MAU, and new users. | Owner-only |
| `$stats report [days]` | Period-over-period health report with message/user deltas, rising and cooling channels, role mix, and peak UTC activity window. | Owner-only |
| `$stats channels [days]` | Top-channel message-volume chart. | Owner-only |
| `$stats compare #a #b [#c ...] [days]` | Line chart comparing daily message volume across 2-5 channels. | Owner-only |
| `$stats topusers [days]` | Top 10 most active users by message count, active days, and messages per active day. | Owner-only |
| `$stats roles [days]` | Daily message-volume chart split by native-role type. | Owner-only |
| `$stats growth [weeks]` | New-user growth chart with total tracked users and MAU. | Owner-only |
| `$stats heatmap [days]` | Hour-by-day activity heatmap in UTC. | Owner-only |
| `$myclock` (alias `$reloj`) | Post a button that shows the clicker their personal 30-day activity clock (a radial hour-of-day chart). Self-serve: any member, own clock only. | None |

`days` is clamped to 1-90. `weeks` for `$stats growth` is clamped to
1-52.

## Activity Clock (`$myclock`)

`$myclock` posts a public message with a single **Ver mi reloj** button.
Anyone can click it, and each clicker gets their own ephemeral clock, so
one posted message serves the whole channel.

The clock is a radial hour-of-day histogram over the last 30 days: 24
petals, `00` at the top going clockwise. A petal's length and colour are
both keyed to that hour's share of the busiest hour, so the peak hour is
the longest and darkest.

Under a rendered clock are two buttons: **Publicar en el canal** shares it
publicly in the current channel (attributed to its owner; disables itself
after posting so it can't double-post), and **Cambiar zona horaria**
re-opens the timezone picker.

### Timezone

Discord exposes no user timezone (only an interface *locale*, which is a
language tag, not an offset), so the clock asks once. On first use the
clicker picks a whole-hour UTC offset from a dropdown; each option shows
the wall-clock time it implies right now, and the prompt embeds the
clicker's own local time (`<t:…:t>`) as the reference to match against.
The choice is saved in `user_clock_prefs` and reused on later clicks (a
**Cambiar zona horaria** button re-opens the picker). Whole-hour offsets
keep the chart exactly aligned to the UTC hour buckets the data lives in,
so no timezone database is needed. The default offset is
`STATS_CLOCK_TZ_OFFSET` (env, default `+1`).

The renderer (`cogs/stats_cog/clock.py`) is Pillow, following the repo's
super-sample-then-LANCZOS convention, and runs via `asyncio.to_thread`.

## Scheduled Reports

Set `STATS_REPORT_CHANNEL_ID` to post a weekly `$stats report 7` digest to
a private admin channel. `STATS_WEEKLY_REPORT_DAY` uses Python weekday
numbering (`0` = Monday, `6` = Sunday), and
`STATS_WEEKLY_REPORT_HOUR_UTC` controls the UTC posting hour.

## Data Model

- `channel_stats`: hourly message counts per channel and native-role type.
- `user_message_counts`: hourly message counts per user.
- `user_activity`: first seen, last seen, and latest native-role type per
  user.
- `user_clock_prefs`: each user's saved whole-hour UTC offset for
  `$myclock` (so the timezone picker is a one-time step).

`StatsCog.on_message` writes all three updates through
`StatsMixin.track_message_stats()` so a message is either fully represented
in stats or not represented at all.
