# Relay (`relay_cog`)

Owner-only message relay to other guilds and channels.

## Overview

The relay cog provides a single command (`$parrot`) that sends a message
to a specified guild + channel. Useful for announcing updates,
testing, or relaying information across servers without switching
accounts.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$parrot [guild_id] [channel_id] <message>` | Send a message to a channel. Defaults to the current channel if no IDs provided. | Owner-only |

## Usage examples

```
$parrot Hello, world!
```
Sends "Hello, world!" to the current channel (trivial use case).

```
$parrot 123456789012345678 987654321098765432 Test message
```
Sends "Test message" to channel `987654321098765432` in guild
`123456789012345678`.

## Implementation notes

- Guild and channel IDs are detected by checking if the first two tokens
  are snowflake-like (17+ digit numbers).
- The bot checks:
  - Guild exists and bot is a member.
  - Channel exists in that guild.
  - Channel is a text channel.
  - Bot has `send_messages` permission in that channel.
- All `$parrot` invocations are logged with invoker, source location,
  and target location.

## Security

- Owner-only via `@commands.is_owner()`.
- No message filtering or sanitization — the owner is trusted.

## Related

- [`./admin.md`](./admin.md) — other owner-only utilities.
