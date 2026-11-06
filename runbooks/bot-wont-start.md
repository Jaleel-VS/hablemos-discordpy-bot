# Bot is offline or won't start

**When:** the Lightsail service is `RUNNING` but the bot isn't online, or a deploy failed.
**Last verified:** 2026-11-06

## Steps

1. Read the latest logs (`read-logs.md`). Match what you see:

   | Log line | Go to |
   |---|---|
   | `Discord rejected the bot token`, `LoginFailure` | `token-reset.md` |
   | `Discord rejected the privileged intents`, `PrivilegedIntentsRequired` | `intents-rejected.md` |
   | `asyncpg` errors, `Database unavailable after 5 attempts` | step 2 |
   | `Failed to load extension`, `ImportError`, `NameError` | step 3 |
   | A PostgreSQL error while the schema initializes | step 4 |
   | `Missing` or `required` env var error | step 5 |
   | `already owns the bot session`, `idling until this container is stopped` | step 6 |

2. **Database.** `setup_hook` tries 5 times (1, 2, 4, 8 s apart), then exits
   without logging in. Check the `hablemos-postgres` state
   (`aws lightsail get-relational-database --region us-east-1 --relational-database-name hablemos-postgres`),
   the `DATABASE_URL` secret, and `psql "$DATABASE_URL" -c "SELECT 1;"`.
3. **Cog load failure.** The bot keeps running and skips the broken cog. Fix the
   import. A new cog needs `cogs/<name>_cog/__init__.py` and `setup(bot)` in
   `cogs/<name>_cog/main.py`.
   To keep a cog off without a deploy: `$cog disable <name>_cog`.
4. **Schema.** `initialize_schema` runs on every start (`db/schema.py`). A failed
   statement aborts startup (after the 5 `setup_hook` attempts); the log shows the
   PostgreSQL error. Fix the SQL. Destructive changes belong in a script under
   `scripts/`, unless they drop a retired feature's tables with `DROP TABLE IF EXISTS`.
5. **Env vars.** `BOT_TOKEN` and `DATABASE_URL` are required (`config.py`).
   Deploy secrets: `deploy/README.md`.
6. **Newer deploy owns the session.** This container's `DEPLOY_VERSION` is older than
   the one in `bot_instance`, so it won't log in (`cogs/utils/instance_guard.py`). That's
   expected for a container being replaced. If it's the only one left, redeploy or roll
   back with the scripts (`deploy.md`); both stamp a fresh version.

## Verify

The logs show `Shard ID None has connected to Gateway`, and the bot is online in Discord.
