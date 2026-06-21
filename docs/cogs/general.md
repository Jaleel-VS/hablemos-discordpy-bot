# General (`general_cog`)

Core bot commands: help, info, ping, invite.

## Overview

The general cog provides essential bot functionality that doesn't fit in
a feature-specific cog. The `/help` command is the main entry point for
users to discover what the bot can do.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `/help [category]` | View all commands or a specific cog's commands. Lists slash + prefix commands (excluding owner-only). | None | None |
| `/info` | Show bot info: uptime, guilds, latency, code stats. | None | None |
| `/ping` | Simple latency check. | None | None |
| `$invite` | Post the bot invite link (if configured). | None | None |

## Configuration

| Constant / Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `INVITE_LINK` | `cogs/general_cog/config.py` | unset | Bot invite URL (shown by `$invite`). |
| `REPO` | `cogs/general_cog/config.py` | GitHub URL | Link to the bot's source code (shown in `/info`). |
| `BOT_AUTHOR_ID` | `cogs/general_cog/config.py` | (baked-in) | Discord user ID of the bot author (shown in `/info`). |
| `DPY` | `cogs/general_cog/config.py` | discord.py docs URL | Link to discord.py documentation. |
| `HIDDEN_COGS` | `cogs/general_cog/main.py` | `{AdminCog, General, DatabaseCommands, RelayCog, AskCog}` | Cogs excluded from `/help` output. |

## `/help` behavior

- Shows all visible cogs with their slash and prefix commands.
- Owner-only commands (detected via `@is_owner()` check) are excluded.
- If `[category]` is provided, shows only that cog's commands.
- Discord embeds allow at most 25 fields. When there are more visible
  cogs than fit, the first 24 are shown as fields and the remainder are
  listed in a final **More categories** field pointing to
  `/help <category>`.
- Commands are formatted as `` `/command` — description `` or
  `` `$command` — description ``.
- Groups (like `/league`) show the group name + description, then
  subcommands.

## `/info` display

- Bot uptime (since last restart).
- Number of guilds and total users.
- API latency (WebSocket ping).
- Code stats: lines of code in `cogs/` and `db/`.
- Links to the repo, bot author, and discord.py docs.

## Implementation notes

- The `_collect_cog_entries` function walks all cogs and their commands
  to build the help embed.
- `walk_app_commands()` is used to recursively find all slash commands,
  including those in groups/subgroups.
- Code stats are computed on-demand by walking `.py` files with
  `pathlib` and counting non-blank lines.

## Related

- [`../commands.md`](../commands.md) — full user command reference.
- [`../admin.md`](../admin.md) — admin commands (hidden from `/help`).
