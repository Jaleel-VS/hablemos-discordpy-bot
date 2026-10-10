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
- **Spotify activity.** When someone runs `$spotify`, the bot reads that
  member's current Spotify activity to render a "now playing" card. It does
  not store this.

## What the bot stores

- **Discord IDs** (user, channel and server IDs) linked to activity counts,
  game results, league standings and command usage.
- **Text you save on purpose**, such as vocabulary notes you create with
  the bot's commands.
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
- To delete everything stored about you, contact a moderator in the server
  or open an issue at
  <https://github.com/Jaleel-VS/hablemos-discordpy-bot/issues>. The
  maintainer will delete your data within 30 days.

## Changes

Changes to this policy are published in this file. The commit history shows
every revision.
