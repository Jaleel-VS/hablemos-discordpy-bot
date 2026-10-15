# A command is missing or a cog isn't loaded

**When:** a command says "not found", a slash command doesn't appear, or a removed one still shows.
**Last verified:** 2026-10-15

## Steps

1. `$cog list` (owner) shows each cog as loaded, disabled, unloaded or protected.
2. **Disabled in the database:** `$cog enable <name>_cog` (for example `league_cog`), then
   `$cog reload <name>_cog`. `$cog disable` persists across restarts. `unload` does not.
3. **Disabled in code:** `ENABLED = False` in `cogs/<name>_cog/config.py` skips the cog
   unless the database enables it.
4. **Needs a key:** the Gemini cogs (`ask`, `breakdown`, `conversation`, `practice`,
   `summary`) don't load without `GEMINI_API_KEY`, which production doesn't pass.
5. **Slash commands** are never synced on startup (rate limits). Run `$sync` (owner):
   - `$sync` syncs globally. Propagation can take up to an hour.
   - `$sync <guild_id>` syncs only commands defined for that guild (such as `/league`), immediately.
     It does not copy global commands into the guild.
   - Error 50240 (Activity entry point conflict) stops the global sync without changing guilds.
     Inspect the application's Entry Point configuration before retrying; do not blindly clear it.
6. Prefix commands (`$...`) need the Message Content intent (`intents-rejected.md`).

## Duplicate or stale commands

- Reload Discord first, but inspect registrations before assuming a client-cache problem.
- Using the application's bot credentials, GET `/applications/<app_id>/commands` and
  `/applications/<app_id>/guilds/<guild_id>/commands` from the Discord API. Compare `(type, name)`
  and IDs. Server admin permissions alone cannot delete the application's registrations.
- Keep one global registration per `(type, name)`. For same-scope duplicates, compare definitions
  and permission overrides before deleting only redundant IDs. Do not wipe the entire tree.
- Delete matching guild copies only when the global command is intended for that server and no
  command-specific permissions would be lost. Preserve guild-only commands such as `/league`
  and any Activity Entry Point (type 4). DELETE uses the corresponding GET path plus `/<command_id>`.
- Verify both GET responses afterward. Historical `$sync <guild_id>` copied globals into the guild;
  deploy the scoped-sync fix and restart the bot before syncing again, to clear those in-memory copies.


## Verify

`$cog list` shows the cog as loaded, and the command appears in Discord.
