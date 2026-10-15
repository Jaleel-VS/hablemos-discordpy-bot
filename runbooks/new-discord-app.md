# Move the bot to a new Discord application

**When:** the old app lost its privileged intents, its token can't be recovered, or you
want a clean app. The bot and the Activity run under one application, so both move.
**Last verified:** 2026-10-15 (command-sync behavior; portal steps not re-run)

Database data carries over. It is keyed by user ID.

## Steps

1. **Portal:** create the app. **Bot** → switch on the three privileged intents. Switch
   **Public Bot** off, unless the person adding the bot isn't the app owner (step 5).
2. **Bot token:** **Bot** → copy the token, then `gh secret set BOT_TOKEN`
   (`token-reset.md` explains why it is entered at a prompt).
3. **Repo:** set the new application ID as the default of `BOT_CLIENT_ID` in
   `cogs/general_cog/config.py`. It feeds the `$invite` link. The ID is public.
4. **Activity:** `gh secret set DISCORD_CLIENT_ID` and `gh secret set DISCORD_CLIENT_SECRET`
   (the frontend build reads the client ID from the first), then follow `activity-setup.md`
   and redeploy the Activity (`deploy.md`).
5. **Add the bot.** The person needs **Manage Server**. With **Public Bot** off, only the
   app owner can add it. If those are two people, switch **Public Bot** on, let the admin
   add the bot, then switch it off. While it is on, anyone with the link can add the bot.
   ```
   https://discord.com/oauth2/authorize?client_id=<APP_ID>&scope=bot%20applications.commands&permissions=275146730560
   ```
   The permissions are: View Channels, Send Messages (and in threads), Embed Links, Attach
   Files, Read Message History, Add Reactions, Use External Emojis, Manage Messages
   (intro and command cleanups), Manage Roles (League champion role).
6. **Role:** in Server Settings → Roles, move the bot's role above the roles it manages
   (the champion role). If `automod_watch_cog` is enabled, the role also needs Manage Server.
7. **Slash commands:** run `$sync` for global commands and `$sync <guild_id>` for guild-only
   commands such as `/league`. A global Activity entry point conflict no longer falls back to
   copying globals into the guild; see `commands-missing.md`. Commands are registered per application.
8. **Panels:** re-post what the old bot posted (`$almightypanel`, `$langexpanel`, and any
   other persistent view). Buttons on the old bot's messages stay dead.
9. Remove the old bot from the server.

## Verify

The logs show `Shard ID None has connected to Gateway`. `$help` answers. `/league` appears.
