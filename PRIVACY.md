# Hablemos Privacy Policy

_Last updated: 2026-10-10_

Hablemos is a Discord bot for the
[Spanish-English Learning Server](https://discord.gg/spanish-english). This
policy explains what data the bot collects, why, and how to have it removed.

## What the bot reads

- **Messages in channels it can see.** The bot reads messages to recognise
  `$` commands, check answers in games, and count activity for the Language
  League and server stats. It does not store the text of these messages.
- **Member information.** The bot reads member IDs, display names and roles
  to show leaderboards, stats and quote images, and to alert staff about
  AutoMod flags.
- **Spotify activity.** Off by default. If you run `$spotify on`, the bot
  reads your current Spotify activity when someone runs `$nowplaying` or
  `$np2`, to render a "now playing" card. It does not store this.

## What the bot stores

- **Discord IDs** (user, channel and server IDs) linked to activity counts,
  game results, league standings and command usage.
- **Usernames and display names**, saved alongside notes, leaderboard
  entries and game scores so they can be shown later.
- **Message counts** per user, channel and hour, used for server stats.
  The text of these messages is not stored.
- **Who replies to or mentions whom** (user IDs and channel only), used
  for staff interaction analysis. Deleted after 90 days.
- **Your Spotify sharing setting** (whether you ran `$spotify on`).
- **Text you give the bot on purpose**: vocabulary notes you save with
  `/vocab`, and the answers you type during the dictation game.
- **Command usage metrics** (which command, when, by which user ID). Raw
  entries are rolled up into daily totals after 30 days.

The bot does not store your email, IP address, or private messages beyond
the commands you send it.

## Third-party services

Some features send text to Google Gemini to generate a response. These
include AI conversations, sentence breakdowns, practice exercises and
moderator-requested conversation summaries. Only the text needed for that
request is sent. Google processes it under its own terms.

Data is stored in a PostgreSQL database hosted on Amazon Web Services.

## Who can see your data

Leaderboards, stats and game results are visible to members of the server.
Server staff and the bot's maintainer can access the database. The bot does
not sell or share data with anyone else.

## Removing your data

- Delete individual vocabulary notes with `/vocab delete <id>`.
- Run `/league leave` to stop Language League activity tracking.
- Run `$spotify off` to stop the bot showing your Spotify activity.
- Run `$quoteme off` to stop others from making quote images of your
  messages.
- **Delete everything stored about you** with `/deletemydata`. The bot
  shows what will be removed and asks you to confirm. Deletion is
  immediate and can't be undone.
- `/deletemydata` keeps moderation records (bans, restrictions,
  anti-spam cooldowns) and your quote opt-out, so deleting data can't
  lift a ban or make you quotable again.
- If you can't run the command (for example, you left the server),
  contact a moderator in the server or open an issue at
  <https://github.com/Jaleel-VS/hablemos-discordpy-bot/issues>. The
  maintainer will delete your data within 30 days.

## Changes

Changes to this policy are published in this file. The commit history shows
every revision.
