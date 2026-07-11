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
| `$stats topusers [days]` | Top 10 most active users by message count, active days, and messages per active day. | Owner-only |
| `$stats roles [days]` | Daily message-volume chart split by native-role type. | Owner-only |
| `$stats growth [weeks]` | New-user growth chart with total tracked users and MAU. | Owner-only |
| `$stats heatmap [days]` | Hour-by-day activity heatmap in UTC. | Owner-only |

`days` is clamped to 1-90. `weeks` for `$stats growth` is clamped to
1-52.

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

`StatsCog.on_message` writes all three updates through
`StatsMixin.track_message_stats()` so a message is either fully represented
in stats or not represented at all.
