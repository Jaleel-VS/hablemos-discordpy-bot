# A command is missing or a cog isn't loaded

**When:** a command says "not found", a slash command doesn't appear, or a removed one still shows.
**Last verified:** 2026-10-11

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
   - `$sync <guild_id>` copies the global commands to that guild. It is instant.
   - Guild-scoped groups (`/league`) need the guild sync.
   - Error 50240 (Activity entry point conflict) makes `$sync` fall back to the current guild.
6. Prefix commands (`$...`) need the Message Content intent (`intents-rejected.md`).

## Verify

`$cog list` shows the cog as loaded, and the command appears in Discord.
